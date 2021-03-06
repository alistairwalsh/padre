Organization of the Data
=========================

Principles
-------------
Important features of how the data is organized:

* The majority of the data tree is read-only, it can be referenced, but not changed in-place
* There is a separate directory to store individual analyses in. These directories are read-write
  and all derived data go in those directories.
* Because the data is diverse and many subjects have idiosyncrasies, there are no static lists of subjects.
  You can request lists from the library, meeting whatever criteria you specify.


Directory structure
-----------------------

	::
		
		Data/
		|-- [subj_id]/
		|   |-- [subj_id].json				# config file, containing subject meta-data
		|   |
		|   |-- raw/				 	# directory with all of the raw data, unorganized
		|   |-- sessions/				# data organized by scanning "session",
		|	|					# as in, one physical visit to the scanner
		|	|-- [session_name]/	
		|		|-- [datasets]		# all of the datasets, arbitrarily named
		|		|-- [scan_sheets]
		|		|-- [behavioral files]
		|		|-- [other meta]	# other files associated with a session
		|		|-- ...
		|-- ..
	
	
	
		Shared/
		|-- Atlases/					# standard atlas volumes
		|   |-- atlases.json				# file describing the atlases
		|   |-- [datasets]
		|
		|-- Stimfiles/					# shared stimfiles (the same for each subject)
		    |-- stimfiles.json				# file describing the stimfiles
		    |-- [files]
		

Subject Objects
----------------

Most of the data from the library is returned in the form of :doc:`subject`. These objects contain
the subject number, meta-data about the subject, as well as the disk location of all files associated
with the subject. The information that is populated into these objects comes from the [subj id].json
file in each subject directory. See the :doc:`subject` page for details on this class.