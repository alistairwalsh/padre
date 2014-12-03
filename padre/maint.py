import padre as p
import os,shutil

def strip_directories(s):
    '''strip fixed leading directories and duplicate files from subjects'''
    new_sess = dict(s.sessions)
    for sess in new_sess:
        for label in new_sess[sess]['labels']:
            new_sess[sess]['labels'][label] = list(set([os.path.basename(x) for x in new_sess[sess]['labels'][label]]))
    s.sessions = new_sess
    s.save()

def create_subject(subject_id):
    ''' creates a new subject (loads old JSON if present and valid) '''
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
    del(subj.sessions[session_name])
    if purge:
        session_dir = os.path.join(p.sessions_dir(subj),session_name)
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)
    subj.save()

def import_raw(subj,new_dir,remove=False):
    '''copies the directory ``dir`` into the raw directory, and deletes original if ``remove`` is ``True``'''
    dest_dir = os.path.join(p.raw_dir(subj),os.path.split(new_dir.rstrip('/'))[1])
    if os.path.exists(dset_dir):
        raise OSError('Cannot import "%s" into subject %s - directory already exists' % (new_dir,subj))
    if remove:
        shutil.move(new_dir,dest_dir)
    else:
        shutil.copytree(new_dir,dest_dir)

def rename(subject_id,new_subject_id,deep=False):
    subj = Subject.load(subject_id)
    if subj:
        try:
            os.rename(p.subject_dir(subject_id),p.subject_dir(new_subject_id))
        except OSError:
            nl.notify('Error: filesystem reported error moving %s to %s' % (subject_id,new_subject_id),level=nl.level.error)
        else:
            subj.subject_id = new_subject_id
            subj.save()
            if deep:
                for dset in subj.dsets(include_all=True):
                    if str(subj) in os.path.basename(dset):
                        new_name = os.path.join(os.path.dirname(dset),os.path.basename(dset).replace(args.subject,args.new_name))
                        try:
                            os.rename(dset,new_name)
                        except OSError:
                            nl.notify('Error: filesystem reported error moving %s to %s' % (subj,args.new_name),level=nl.level.error)                            
            else:
                nl.notify('Successfully renamed %s to %s (NOTE: none of the dataset names are changed in this process)' % (subj,args.new_name))

def import_to_padre(subject_id,session,dsets,raw_data=[],dir_prefix=''):
    fuzzyness = 80
    subj = create_subject(subject_id)
    try:
        subj.new_session(session)
    except p.subject.SessionExists:
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
