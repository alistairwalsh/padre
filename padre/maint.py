import neural as nl
import padre as p
import os,shutil,glob,subprocess,datetime
from fuzzywuzzy import process,fuzz

_git_ignore = [
    '*','!Data','!Data/*',
    '!Data/*/*.%s' % p.json_ext,
    '*.7z','*.dmg','*.gz','*.iso','*.jar','*.rar','*.tar','*.tgz','*.tbz','*.zip',
    '.DS_Store','.DS_Store?','._*','.Spotlight-V100','.Trashes','ehthumbs.db','Thumbs.db'
]

import imp
c = None
padre_config_file = os.path.join(p.padre_root,'padre_config.py')
if os.path.exists(padre_config_file):
    c = imp.load_source('padre_config',padre_config_file)

def commit_database(wait=True):
    '''database is stored as distributed jsons that are tracked by git -- this saves a new commit'''
    with nl.run_in(p.padre_root):
        if not os.path.exists('.git'):
            subprocess.check_call(['git','init'])
            with open('.gitignore','w') as f:
                f.write('\n'.join(_git_ignore))
        proc = subprocess.Popen(['git','add'] + glob.glob('Data/*/*.%s' % p.json_ext),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        proc.wait()
        proc = subprocess.Popen(['git','commit','-am','library commit'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if wait:
            proc.wait()

class commit_wrap:
    '''do a commit before and after this'''
    def __enter__(self):
        commit_database()
    
    def __exit__(self, type, value, traceback):
        commit_database()

def strip_directories(s):
    '''strip fixed leading directories and duplicate files from subjects'''
    with commit_wrap():
        new_sess = dict(s.sessions)
        for sess in new_sess:
            for label in new_sess[sess]['labels']:
                new_sess[sess]['labels'][label] = list(set([os.path.basename(x) for x in new_sess[sess]['labels'][label]]))
        s.sessions = new_sess
        s.save()

def create_subject(subject_id):
    ''' creates a new subject (loads old JSON if present and valid) '''
    with commit_wrap():
        subj = None
        if os.path.exists(p.subject_json(subject_id)):
            subj = p.Subject.load(subject_id)
            if subj==None:
                subj = p.Subject(subject_id)              
        else:
            subj = p.Subject(subject_id)
        subj.init_directories()
        subj.save()
    return subj

def delete_subject(subject_id):
    if not os.path.exists(p.trash_dir):
        os.makedirs(p.trash_dir)
    new_dir = os.path.join(p.trash_dir,'%s-%s' % (subject_id,datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S').format()))
    while os.path.exists(new_dir):
        new_dir += '_1'
    try:
        shutil.move(p.subject_dir(subject_id),new_dir)
    except OSError,IOError:
        nl.notify('Error moving subject directory %s to the trash' % subject_id,level=nl.level.error)
    try:
        del(p.subject._all_subjects[str(subject_id)])
    except KeyError:
        pass
    
class SessionExists(LookupError):
    pass

def new_session(subj,session_name):
    ''' create a new session
    
    Inserts the proper data structure into the JSON file, as well as creating
    the directory on disk.
    '''
    with commit_wrap():
        if session_name in subj._sessions:
            raise SessionExists
        session_dir = os.path.join(p.sessions_dir(subj),session_name)
        if not os.path.exists(session_dir):
            os.makedirs(session_dir)
        subj._sessions[session_name] = {'labels':{}}

def delete_session(subj,session_name,purge=False):
    ''' delete a session
    
    By default, will only delete the references to the data within the JSON file.
    If ``purge`` is given as ``True``, then it will also delete the files from
    the disk (be careful!). ``purge`` will also automatically call ``save``.'''
    with commit_wrap():
        del(subj._sessions[session_name])
        if purge:
            session_dir = os.path.join(p.sessions_dir(subj),session_name)
            if os.path.exists(session_dir):
                shutil.rmtree(session_dir)
        subj.save()

def import_raw(subj,new_dir,remove=False):
    '''copies the directory ``dir`` into the raw directory, and deletes original if ``remove`` is ``True``'''
    with commit_wrap():
        dest_dir = os.path.join(p.raw_dir(subj),os.path.split(new_dir.rstrip('/'))[1])
        if os.path.exists(dset_dir):
            raise OSError('Cannot import "%s" into subject %s - directory already exists' % (new_dir,subj))
        if remove:
            shutil.move(new_dir,dest_dir)
        else:
            shutil.copytree(new_dir,dest_dir)

def rename(subject_id,new_subject_id):
    with commit_wrap():
        subj = p.load(subject_id)
        if subj:
            try:
                os.rename(p.subject_dir(subject_id),p.subject_dir(new_subject_id))
            except OSError:
                nl.notify('Error: filesystem reported error moving %s to %s' % (subject_id,new_subject_id),level=nl.level.error)
            else:
                subj._subject_id = new_subject_id
                subj.save()
                if os.path.exists(p.subject_json(subj)):
                    try:
                        os.remove(os.path.join(p.subject_dir(subj),os.path.basename(p.subject_json(subject_id))))
                    except OSError:
                        pass
                    try:
                        del(p.subject._all_subjects[str(subject_id)])
                    except KeyError:
                        pass
    p.subject._index_one_subject(new_subject_id)

def merge_attr(f,t):
    if t==None or t=='' and not (f==None or f==''):
        t=f

dset_i = lambda label_dict,dset_fname: [x['filename'] for x in label_dict].index(dset_fname)

def merge_session(subj_from,subj_to,sess):
    if sess not in subj_to._sessions:
        subj_to._sessions[sess] = subj_from._sessions[sess]
    else:
        for k in subj_from._sessions[sess]:
            if k!= 'labels':
                if k in subj_to._sessions[sess]:
                    merge_attr(subj_from._sessions[sess][k],subj_to._sessions[sess][k])
                else:
                    subj_to._sessions[sess][k] = subj_from._sessions[sess][k]
        for label in subj_from._sessions[sess]['labels']:
            if label not in subj_to._sessions[sess]['labels']:
                subj_to._sessions[sess]['labels'][label] = []
            for dset in subj_from._sessions[sess]['labels'][label]:
                try:
                    to_i = dset_i(subj_to._sessions[sess]['labels'][label],dset['filename'])
                    subj_to._sessions[sess]['labels'][label][to_i] = dict(dset.items() + subj_to._sessions[sess]['labels'][label][to_i].items())
                except ValueError:
                    subj_to._sessions[sess]['labels'][label].append(dset)
    del(subj_from._sessions[sess])
    new_sess_dir = os.path.join(p.sessions_dir(subj_to),sess)
    from_sess_dir = os.path.join(p.sessions_dir(subj_from),sess)
    if not os.path.exists(new_sess_dir):
        os.makedirs(new_sess_dir)
    for r,ds,fs in os.walk(from_sess_dir):
        for f in fs:
            dset_f = os.path.join(new_sess_dir,f)
            if not os.path.exists(dset_f):
                os.rename(os.path.join(r,f),dset_f)
    if len(os.listdir(from_sess_dir))==0:
        os.rmdir(from_sess_dir)
    else:
        new_dir = os.path.join(p.trash_dir,'%s-%s-%s' % (subj_from,sess,datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S').format()))
        while os.path.exists(new_dir):
            new_dir += '_1'
        os.rename(from_sess_dir,new_dir)
    subj_from.save()
    subj_to.save()

def merge(subject_id_from,subject_id_into):
    nl.notify('Trying to merge %s into %s' % (subject_id_from,subject_id_into))
    with commit_wrap():
        subj_from = p.load(subject_id_from)
        subj_to = p.load(subject_id_into)
        if subj_from and subj_to:
            merge_attr(subj_from.include,subj_to.include)
            merge_attr(subj_from.notes,subj_to.notes)
            subj_to.meta = dict(subj_from.meta.items() + subj_to.meta.items())
            sess_keys = subj_from._sessions.keys()
            for sess in sess_keys:
                merge_session(subj_from,subj_to,sess)
            subj_to.save()
            delete_subject(subj_from)

def guess_label(filename,fuzzyness = 80):
    inverted_labels = {}
    for label in c.dset_labels:
        for dset in c.dset_labels[label]:
            inverted_labels[dset] = label
    for label in inverted_labels:
        if fuzz.partial_ratio(filename.lower(),label.lower())>fuzzyness:
            return inverted_labels[label]
    label_match = process.extractOne(filename,inverted_labels.keys())
    if label_match[1] >= fuzzyness:
        return inverted_labels[label_match[0]]
    return 'unsorted'


def import_to_padre(subject_id,session,dsets,raw_data=[],dir_prefix=''):
    with commit_wrap():
        subj = create_subject(subject_id)
        try:
            new_session(subj,session)
        except SessionExists:
            pass
        session_dict = dict(subj._sessions[session])
        session_dict['unverified'] = True
        session_dict['date'] = datetime.datetime.strftime(nl.date_for_str(session),'%Y-%m-%d')
        for full_dset in sorted(dsets,key=lambda x:(int(os.path.basename(x).split('-')[1]),int(os.path.basename(x).split('-')[2]))):
            dset = {}
            dset['filename'] = os.path.basename(full_dset)
            if dset['filename'] not in [x.__str__(False) for x in subj.dsets(include_all=True)]:
                dset['md5'] = nl.hash(full_dset)
                dset['complete'] = True
                dset['meta'] = {}
                label = guess_label(dset['filename'].split('-')[3])
                if label not in session_dict['labels']:
                    session_dict['labels'][label] = []
                session_dict['labels'][label].append(dset)
                dset_fname = os.path.join(p.sessions_dir(subj),session,dset['filename'])
                if not os.path.exists(dset_fname):
                    shutil.move(full_dset,dset_fname)
        for raw in raw_data:
            try:
                shutil.move(os.path.join(dir_prefix,'raw',raw),p.raw_dir(subj))
            except:
                pass
        subj._sessions[session] = session_dict
        subj.save()

def dsets_identical(dset1,dset2):
    '''Tests if given datasets are identical'''
    max_tolerance = 1.0
    
    with nl.notify('Comparing %s with %s' % (dset1,dset2)):
#        info = [nl.afni.dset_info(dset) for dset in [dset1,dset2]]
#        for param in ['reps','voxel_size','voxel_dims']:
#            if getattr(info[0],param) != getattr(info[1],param):
#                nl.notify('Datasets differ in at least %s (%s vs. %s)' % (param,getattr(info[0],param),getattr(info[1],param)),level=nl.level.warning)
#                return False
        max_diff = nl.max_diff(dset1,dset2)
        if max_diff > max_tolerance:
            nl.notify('Datasets have a maximal differenence >%.1f (max_diff = %.1f)' % (max_tolerance, max_diff),level=nl.level.warning)
            return False
        
        if max_diff==0:
            nl.notify('Datasets appear to be identical')
            return True
        
        nl.notify('Datasets are minimally different (max_diff = %.1f)' % max_diff)
        return True

def sessions_identical(subj1,sess1,subj2,sess2):
    '''Tests the given sessions to make sure the datasets are the same'''
    dsets1 = [os.path.basename(str(x)) for x in subj1.dsets(session=sess1)]
    dsets2 = [os.path.basename(str(x)) for x in subj2.dsets(session=sess2)]
    dsets = list(set(dsets1+dsets2))
    return_val = True
    with nl.notify('Comparing sessions %s.%s and %s.%s:' % (subj1,sess1,subj2,sess2)):
        for dset in dsets:
            if not dsets_identical(os.path.join(p.sessions_dir(subj1),sess1,dset),os.path.join(p.sessions_dir(subj2),sess2,dset)):
                return_val = False
                continue
    return return_val

def synchronize_to_disk(subj,add_missing=True,delete_duplicates=True,delete_missing=True):
    '''Will try to clean up a subject's JSON file based on what files actually exist on disk
    
    :add_missing:           adds new JSON entries for files that exist on disk but aren't listed
    :delete_duplicates:     delete duplicate JSON entries if they refer to the same file
    :delete_missing:        delete JSON entries that have no file on disk'''
    
    def dset_in_dict(fname,l):
        return len([x for x in nl.flatten(l.values()) if fname==x['filename']])>1
    
    with nl.notify('Trying to clean up subject %s' % subj):
        s = p.load(subj)
        if s==None:
            nl.notify('Error: couldn\'t load subject %s!' % subj,level=nl.level.error)
            return False
        with commit_wrap():
            sess_on_disk = os.listdir(os.path.join(p.sessions_dir(s)))
            sess_extra_JSON = list(set(s._sessions.keys()) - set(sess_on_disk))
            sess_extra_disk = list(set(sess_on_disk) - set(s._sessions.keys()))
            if len(sess_extra_disk)>0:
                if add_missing:
                    for sess in sess_extra_disk:
                        nl.notify('Creating missing session %s' % sess,level=nl.level.warning)
                        new_session(s,sess)
                else:
                    nl.notify('Warning: found sessions on disk with no entries: %s' % (' '.join(sess_extra_disk)),level=nl.level.warning)
            if len(sess_extra_JSON)>0:
                if delete_missing:
                    for sess in sess_extra_JSON:
                        nl.notify('Removing session %s (missing from disk)' % sess, level=nl.level.warning)
                        del(s._sessions[sess])
                else:
                    nl.notify('Warning: found sessions missing from disk: %s' % (' '.join(sess_extra_disk)),level=nl.level.warning)
            for sess in s._sessions:
                with nl.notify('Checking session "%s"...' % sess):
                    new_sess = {}
                    for fname in os.listdir(os.path.join(p.sessions_dir(s),sess)):
                        if nl.is_dset(fname):
                            res = s._index_of_dset_named(fname,sess)
                            if res:
                                # At least one copy of this in the old session
                                (_,label,i) = res
                                nl.notify('Found %s' % fname)
                                if label not in new_sess:
                                    new_sess[label] = []
                                new_sess[label].append(s._sessions[sess]['labels'][label][i])
                                del(s._sessions[sess]['labels'][label][i])
                            else:
                                # File on disk, but no entry
                                if add_missing:
                                    nl.notify('Adding new entry for file %s' % fname,level=nl.level.warning)
                                    dset = {}
                                    dset['filename'] = fname
                                    full_dset = os.path.join(p.sessions_dir(s),sess,fname)
                                    dset['md5'] = nl.hash(full_dset)
                                    dset['complete'] = True
                                    dset['meta'] = {}
                                    if 'unsorted' not in new_sess:
                                        new_sess['unsorted'] = []
                                    new_sess['unsorted'].append(dset)
                    for label in s._sessions[sess]['labels']:
                        if len(s._sessions[sess]['labels'][label])>0:
                            # Leftover entries that have no file
                            for dset in s._sessions[sess]['labels'][label]:
                                if dset_in_dict(dset['filename'],new_sess):
                                    # Already have seen this dataset somewhere...
                                    if delete_duplicates:
                                        nl.notify('Deleting duplicate entry for file %s' % dset['filename'],level=nl.level.warning)
                                    else:
                                        nl.notify('Warning: found duplicate entry for file %s (leaving in place)' % dset['filename'],level=nl.level.warning)
                                        new_sess[label].append(dset)
                                else:
                                    # Entry in JSON, but no file on disk
                                    if delete_missing:
                                        nl.notify('Deleting missing dataset %s (no corresponding file on disk)' % dset['filename'],level=nl.level.warning)
                                    else:
                                        nl.notify('Warning: found entry for %s, but no corresponding file on disk (leaving empty entry in place)' % dset['filename'],level=nl.level.warning)
                                        new_sess[label].append(dset)
                    s._sessions[sess]['labels'] = new_sess
            s.save()