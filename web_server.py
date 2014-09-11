import padre as p
from bottle import route,view,run,post,static_file,request

@route('/styles.css')
def css_file():
    return static_file('views/styles.css','.')

@route('/favicon.ico')
def favicon():
    return static_file('views/favicon.ico','.')

@route('/subjects')
@view('list_subjects')
def subjects():
    return {
        'subjects': sorted(p.subjects())
    }

@route('/<subject_id>')
@view('edit_subject')
def subject_list(subject_id):
    return {
        'subject_id': subject_id,
        'subj': p.load(subject_id)
    }

@route('/<subject_id>/<session>')
@view('edit_session')
def edit_session(subject_id,session):
    return {
        'subject_id': subject_id,
        'subj': p.load(subject_id),
        'session': session,
        'labels': p.subject.tasks
    }

@post('/save_session/<subject_id>/<session>')
def save_session(subject_id,session):
    new_subject_id = request.forms.get('new_subject_id')
    if new_subject_id!=subject_id:
        pass

if __name__ == '__main__':
    import socket
    run(host=socket.gethostname(),port=8003)