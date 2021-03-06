#!/usr/bin/env python
''' daemon to automatically collect and organize data into padre'''

import urllib2, re, json, os, shutil, socket, tarfile, tempfile, fnmatch
from dateutil.parser import parse
import neural as nl
import padre as p
from fuzzywuzzy import process

import_location = os.path.join(p.padre_root,'Import')
processed_location = os.path.join(p.padre_root,'Processed')
import_log_file = os.path.join(import_location,'import_log.json')

import imp
c = imp.load_source('padre_config',os.path.join(p.padre_root,'padre_config.py'))

import_log = {}
if not os.path.exists(import_location):
    os.makedirs(import_location)
if os.path.exists(import_log_file):
    with open(import_log_file) as f:
        import_log = json.loads(f.read())

def save_log():
    with open(import_log_file,'w') as f:
        f.write(json.dumps(import_log))

def import_archive(full_file,subject_guess,slice_order='alt+z',sort_order='zt'):
    tmp_dir = tempfile.mkdtemp()
    try:
        padre_dir = full_file.replace(import_location,"PADRE/Import")
        tmp_location = os.path.join(tmp_dir,'_tmp_unarchive')
        out_dir = os.path.join(processed_location,subject_guess)
        for d in [tmp_location,tmp_location + '-sorted']:
            if os.path.exists(d):
                shutil.rmtree(d)
        import_log[padre_dir] = {'modified':os.path.getmtime(full_file)}
        if nl.is_archive(full_file):
            with nl.notify('uncompressing files...'):
                os.makedirs(tmp_location)
                nl.unarchive(full_file,tmp_location)
        else:
            with nl.notify('copying files...'):
                shutil.copytree(full_file,tmp_location)
        with nl.notify('sorting files...'):
            nl.dicom.organize_dir(tmp_location)
        dsets_made = {}
        if os.path.exists(tmp_location + '-sorted'):
            if not os.path.exists(os.path.join(out_dir,'raw')):
                os.makedirs(os.path.join(out_dir,'raw'))
            with nl.run_in(tmp_location + '-sorted'):
                for subdir in os.listdir('.'):
                    if 'dset_ignore_masks' in dir(c):
                        ignore = False
                        for m in c.dset_ignore_masks:
                            if m in subdir:
                                ignore = True
                        if ignore:
                            continue
                    nl.notify('creating dataset from %s' % subdir)
                    import_log[padre_dir][subdir] = {}
                    if not nl.dicom.create_dset(subdir,slice_order,sort_order):
                        import_log[padre_dir][subdir]['error'] = True
                    if os.path.exists(subdir + '.nii.gz'):
                        import_log[padre_dir][subdir]['complete'] = True
                        shutil.move(subdir + '.nii.gz',os.path.join(out_dir,subdir+'.nii.gz'))
                        session_name = subdir.split('-')[1]
                        if session_name not in dsets_made:
                            dsets_made[session_name] = []
                        dsets_made[session_name].append(os.path.join(out_dir,subdir+'.nii.gz'))
                    if 'complete' in import_log[padre_dir][subdir] and import_log[padre_dir][subdir]['complete']:
                        if 'error' in import_log[padre_dir][subdir] and import_log[padre_dir][subdir]['error']:
                            nl.notify('created dataset %s, but Dimon returned an error' % (subdir+'.nii.gz'),nl.level.error)
                        else:
                            nl.notify('successfully created dataset %s' % (subdir+'.nii.gz'))
                    else:
                        nl.notify('failed to create dataset from directory %s' % subdir,level=nl.level.error)
            nl.notify('moving raw data...')
            raw_data = []
            for subdir in os.listdir(tmp_location + '-sorted'):
                out_file = os.path.join(out_dir,'raw',subdir + '.tgz')
                if not os.path.exists(out_file):
                    try:
                        with tarfile.open(out_file,'w:gz') as tgz:
                            tgz.add(os.path.join(tmp_location + '-sorted',subdir))
                    except tarfile.TarError:
                        nl.notify('Error creating compressed raw directory %s' % out_file,level=nl.level.error)
                    else:
                        raw_data.append(subdir + '.tgz')
            for r,ds,fs in os.walk(tmp_location):
                for f in fs:
                    out_file = os.path.join(out_dir,'raw','unsorted',r.lstrip(tmp_location).lstrip('/'),f)
                    if not os.path.exists(out_file):
                        if not os.path.exists(os.path.dirname(out_file)):
                            os.makedirs(os.path.dirname(out_file))
                        shutil.move(os.path.join(r,f),out_file)
                        raw_data.append(os.path.join('unsorted',r.lstrip(tmp_location).lstrip('/'),f))
            nl.notify('importing into padre...')
            for session in dsets_made:
                p.maint.import_to_padre(subject_guess,session,dsets_made[session],raw_data,out_dir)
        else:
            nl.notify('didn\'t find any files...')
    finally:
        shutil.rmtree(tmp_dir,True)
    save_log()
    return dsets_made



def unpack_new_archives(pi):
    new_files = []
    with nl.notify('Scanning PI %s for new archives' % pi):
        for root,dirs,files in os.walk(os.path.join(import_location,pi)):
            for fname in files + dirs:
                full_file = os.path.join(root,fname)
                padre_dir = full_file.replace(import_location,"PADRE/Import")
                if padre_dir not in import_log:
                    # Add in a check for the modification date
                    if any([fnmatch.fnmatch(fname,m) for m in c.archive_masks]):
                        with nl.notify('Found new archive "%s"' % full_file):
                            subject_guess = os.path.basename(os.path.dirname(full_file))
                            nl.notify('guessing the subject number is %s' % subject_guess)
                            dsets = import_archive(full_file,subject_guess)
                            new_files.append({'dir':full_file.lstrip(os.path.join(import_location,pi)).lstrip('/'),'subj':subject_guess,'fname':fname,'dsets':dsets})
    return new_files

def rsync_remote(pi,verify=False):
    with nl.notify('rsync\'ing data for PI %s' % pi):
        opts = c.rsync_options
        if verify:
            opts += 'v'
            nl.notify('If running as a non-administrator, you may be prompted for the server (%s) password' % c.server_name)
        o = nl.run([c.rsync,opts,'-e','ssh -i %s' % c.server_id,'%s/%s' % (c.server_name,pi),import_location])
        if verify:
            if o.return_code!=0:
                nl.notify('Error: Rsync returned status code of %d' % o.return_code,level=nl.level.error)
            else:
                nl.notify('Rsync completed successfully')
            if o.output:
                nl.notify('Output:\n' + o.output)

def email_updates(updates):
    '''Send update email to selected emails when new datsets arrives

    Expects the following to be set in ``padre_config.py``:

    Required:

    :demon_update_emails:       list of emails to send notifications to
    :demon_update_subject:      subject line
    :demon_update_from:         email to list as "From" address
    :demon_update_smtp_server:  SMTP server

    Optional:

    :demon_update_from_name:    name to list as "From"
    :demon_update_username      username for SMTP server (optional)
    :demon_update_password      password for SMTP server (optional)
    :demon_update_template:     method that takes the updated files as a block of text
                                and returns the full text of the email as string.
                                Allows you to add any text you want to frame the email
    '''
    if 'demon_update_emails' not in dir(c):
        return

    update_text = ''
    for pi in updates:
        update_text += pi + ':\n'
        for archive in updates[pi]:
            update_text += '\t%s/%s (subject = %s)\n' % (archive['dir'],archive['fname'],archive['subj'])
            for sess in archive['dsets']:
                update_text += '\t\t%s:\n' % sess
                for dset in archive['dsets'][sess]:
                    update_text += '\t\t\t- %s\n' % os.path.basename(dset)

    try:
        update_text = c.demon_update_template(update_text)
    except:
        pass
    opts = {}
    try:
        opts['from_name'] = c.demon_update_from_name
    except:
        pass
    try:
        opts['username'] = c.demon_update_username
    except:
        pass
    try:
        opts['password'] = c.demon_update_password
    except:
        pass

    nl.notification.enable_email(c.demon_update_from,c.demon_update_smtp_server,**opts)
    nl.notification.email(c.demon_update_emails,update_text,c.demon_update_subject)



if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument('--pi',nargs='?',default=c.pis,choices=c.pis,help="Only run on specified PI's directory")
    parser.add_argument('--rsync',action='store_true',help="Only run the rsync")
    parser.add_argument('--verify',action='store_true',help="Increase verbosity of rsync so you're able to verify it finished properly")
    parser.add_argument('--email',action='store_true',help="Send email with updates")

    args = parser.parse_args()
    updates = {}
    for pi in args.pi:
        rsync_remote(pi,args.verify)
        if args.rsync:
            continue
        updates_pi = unpack_new_archives(pi)
        if len(updates_pi)>0:
            updates[pi] = updates_pi
    if len(updates)>0 and args.email:
        email_updates(updates)
