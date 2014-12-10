import neural as nl
import padre as p
import os,shutil,glob,subprocess

_git_ignore = [
    '*','!Data','!Data/*',
    '!Data/*/*.%s' % p.json_ext,
    '*.7z','*.dmg','*.gz','*.iso','*.jar','*.rar','*.tar','*.tgz','*.tbz','*.zip',
    '.DS_Store','.DS_Store?','._*','.Spotlight-V100','.Trashes','ehthumbs.db','Thumbs.db'
]

def commit_database(wait=True):
    '''database is stored as distributed jsons that are tracked by git -- this saves a new commit'''
    with nl.run_in(p.padre_root):
        if not os.path.exists('.git'):
            subprocess.check_call(['git','init'])
            with open('.gitignore','w') as f:
                f.write('\n'.join(_git_ignore))
        proc = subprocess.Popen(['git','add'] + glob.glob('Data/*/*.%s' % p.json_ext))
        proc.wait()
        subprocess.Popen(['git','commit','-m','library commit'])
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
    
class SessionExists(LookupError):
    pass

def new_session(subj,session_name):
    ''' create a new session
    
    Inserts the proper data structure into the JSON file, as well as creating
    the directory on disk.
    '''
    with commit_wrap():
        if session_name in subj.sessions:
            raise SessionExists
        session_dir = os.path.join(p.sessions_dir(subj),session_name)
        if not os.path.exists(session_dir):
            os.makedirs(session_dir)
        subj.sessions[session_name] = {'labels':[]}

def delete_session(subj,session_name,purge=False):
    ''' delete a session
    
    By default, will only delete the references to the data within the JSON file.
    If ``purge`` is given as ``True``, then it will also delete the files from
    the disk (be careful!). ``purge`` will also automatically call ``save``.'''
    with commit_wrap():
        del(subj.sessions[session_name])
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
                subj.save()
                if os.path.exists(p.subject_json(subj)):
                    try:
                        os.remove(os.path.join(p.subject_dir(subj),os.path.basename(p.subject_json(subject_id))))
                    except OSError:
                        pass
    p.subject._index_one_subject(new_subject_id)

def merge(subject_id_from,subject_id_into):
    with commit_wrap():
        def merge_attr(f,t):
            if t==None or t=='' and not (f==None or f==''):
                t=f
        dset_i = lambda label_dict,dset_fname: [x['filename'] for x in label_dict].index(dset_fname)
        subj_from = p.load(subject_id_from)
        subj_to = p.load(subject_id_to)
        if subj_from and subj_to:
            merge_attr(subj_from.include,subj_to.include)
            merge_attr(subj_from.notes,subj_to.notes)
            subj_to.meta = dict(subj_from.meta.items() + subj_to.meta.items())
            for sess in subj_from._sessions:
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
                new_sess_dir = os.path.join(p.sessions_dir(subj_to),sess)
                if not os.path.exists(new_sess_dir):
                    os.makedirs(new_sess_dir)
                for r,ds,fs in os.walk(os.path.join(p.sessions_dir(subj_from),sess)):
                    for f in fs:
                        dset_f = os.path.join(new_sess_dir,f)
                        if not os.path.exists(dset_f):
                            os.rename(os.path.join(r,f),dset_f)
        subj_to.save()
        delete_subject(subj_from)

def import_to_padre(subject_id,session,dsets,raw_data=[],dir_prefix=''):
    with commit_wrap():
        fuzzyness = 80
        subj = create_subject(subject_id)
        try:
            new_session(subj,session)
        except SessionExists:
            pass
        session_dict = dict(subj._sessions[session])
        session_dict['unverified'] = True
        session_dict['date'] = '-'.join(session[4:],session[4:6],session[6:8])
        inverted_labels = {}
        for label in c.dset_labels:
            for dset in c.dset_labels[label]:
                inverted_labels[dset] = label
        for full_dset in sorted(dsets,key=lambda x:(int(os.path.basename(x).split('-')[1]),int(os.path.basename(x).split('-')[2]))):
            dset = {}
            dset['filename'] = os.path.basename(full_dset)
            if dset['filename'] not in [x['filename'] for x in subj.dsets(include_all=True)]:
                dset['md5'] = nl.utils.hash(full_dset)
                dset['complete'] = True
                dset['meta'] = {}
                label_match = process.extractOne(dset['filename'].split('-')[3],inverted_labels.keys())
                if label_match[1] >= fuzzyness:
                    label = inverted_labels[label_match[0]]
                else:
                    label = 'unsorted'
                if label not in session_dict['labels']:
                    session_dict['labels'][label] = []
                session_dict['labels'][label].append(dset)
                dset_fname = os.path.join(p.sessions_dir(subj),session,dset['filename'])
                if not os.path.exists(dset_fname):
                    shutil.move(full_dset,dset_fname)
        for raw in raw_data:
            shutil.move(os.path.join(dir_prefix,'raw',raw),p.raw_dir(subj))
        subj._sessions[session] = session_dict
        subj.save()
