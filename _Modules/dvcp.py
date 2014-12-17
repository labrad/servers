"""
Create two separate connections to a(two) data_vault server(s).
Access data/parameters for each dataset with one connection, and
create  a new instance of the data/parameters with the other connection.
"""

from numpy import *
import labrad, sys

# from http://code.activestate.com/recipes/577058/
# Prompt the user with a y/n question, return true/false respectively
def query_yes_no(question, default="yes"):
    """
    Ask a yes/no question via raw_input() and return the answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is one of "yes" or "no".
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = raw_input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")


def navigate(dv, path, write=False):
    """
    Attempt to navigate to a specified directory within the given dataVault (dv)
    
    Path must be a list of strings
    
    If write == True, create the directory path specified if it does not exist
    
    Return the extent of desired path that is(was) present upon invocation
    """
    
    # terminus = extent of path that already exists
    if path[0] == ['']: # starting from root
        terminus = ['']
    else:
        terminus = dv.cd() # relative to current location

    for dir in path:
        try:
            # stop updating "terminus" with the first directory that doesn't exist
            terminus = dv.cd(dir)
        except:
            if write:
                dv.mkdir(dir)
                dv.cd(dir)
            else:
                return terminus # exit when the requested directory doesn't exist
    return terminus # exit after all directories have been created/navigated

def recreate_open_dataset(dv_from, dv_to):
    """
    Use dv_to to create a new dataset in the current directory,
    replicating the dataset that is presently open with dv_from.
    
    Return True if the copy was successful
    
    Return False if no data can be read (you may need to re-open the dataset)
    """
    
    # read data and parameters
    data = dv_from.get()
    if not len(data) or not len(data[0]):
        print("No data received from " + dv_from.get_name() + " in " + str(dv_from.cd()) + ".")
        print("Did not copy dataset.")
        return False
    name = dv_from.get_name()
    vars = dv_from.variables()
    params = dv_from.get_parameters()
    comments = dv_from.get_comments()

    # recreate it in the destination data_vault
    dv_to.new(name[8:],vars[0],vars[1])
    dv_to.add(data)
    dv_to.add_parameters(params)
    for i in comments:
        dv_to.add_comment(i[2])
    return True

def recreate_datasets(dv_from, dv_to, exclude = [], write=True):
    """
    Recreate all datasets in the current directory of dv_from
    in the current directory of dv_to.
    
    Do not copy datasets listed in 'exclude'
        e.g. exclude = ['00001 - Title of dataset','00002 - Another dataset']
        
    If write == false, only count the number of datasets
    that would have been copied
    
    Return [number of datasets, number not excluded, number (would have)copied]
    """
    
    # list of datasets in current source directory
    datasets_present = set(dv_from.dir()[1])
    
    # exclude certain datasets
    # would be nice if this was a search/filter, but it only works
    # presently if the names are given exactly.
    datasets_included = datasets_present.difference(exclude)
    
    num_datasets_present = len(datasets_present)
    num_datasets_included = len(datasets_included)
    num_datasets_created = 0

    datasets_included = list(datasets_included)
    datasets_included.sort()

    for x in datasets_included:
        if write:
            dv_from.open(x)
            if recreate_open_dataset(dv_from, dv_to):
                # count how many datasets we copied
                num_datasets_created += 1
        else:
            # count how many datasets we would have tried to copy
            num_datasets_created += 1
        
    return [num_datasets_present, num_datasets_included, num_datasets_created]

def copy_tree(dv_from, dv_to, write=True, exclude=[], root_to=False):
    """
    Recreate the directory structure and datasets from 
    the current directory of dv_from in the current directory of dv_to.
    
    Do not copy subdirectories or datasets listed in 'exclude'
        e.g. exclude = 
        ['Subdirectory_1','00001 - Title of dataset','00002 - Another dataset']
    
    If write == false, only count the number of datasets and directories 
    that would have been copied
    
    Return [number of datasets present in included subdirectories, 
    number of which were not excluded, 
    number of datasets that were(would have been) copied,
    number of subdirectories found,
    number of which were not excluded,
    number of subdirectories that were(would have been) copied]
    """
    
    # To navigate the directory tree structure,this function calls itself in each subdirectory
    
    # recreate datasets in current directory and store output
    [num_datasets_present, num_datasets_included, num_datasets_created] = recreate_datasets(dv_from, dv_to, exclude=exclude, write=write)
    
    # the root of the destination directory structure is
    # passed along to nested instances of the function.
    # otherwise, when write=False, we don't know that we didn't enter
    # the desired destination directory when counting directories to be created
    if root_to == False:
        root_to = dv_to.cd() # only happens on first function call of "copy_tree"
    root_from = dv_from.cd()
    
    # set of subdirectories
    subdirs_present = set(dv_from.dir()[0])
    # set of subdirectories not excluded
    subdirs_included = subdirs_present.difference(exclude)
    
    num_subdirs_present = len(subdirs_present)
    num_subdirs_included = len(subdirs_included)
    num_subdirs_created = 0
    
    out = array([num_datasets_present, num_datasets_included, num_datasets_created,
    num_subdirs_present, num_subdirs_included, num_subdirs_created])
    
    # for each included subdirectory
    for sbd in subdirs_included:
        dv_from.cd(sbd)
        
        # does the target directory exist?
        terminus = navigate(dv_to, root_to+[sbd], write=write)
        if terminus != root_to+[sbd]:
                out[5] += 1 # num_subdirs_created += 1

        # call this function in the subdirectory
        # and add the numbers of datasets/directories
        out += copy_tree(dv_from, dv_to, write=write, exclude=exclude, root_to=root_to)
        
        # go back to the directory we were just in
        dv_from.cd(root_from)
        dv_to.cd(root_to)
    
    # pass the output upwards
    return out
    

def auto_copy(wrap_from, wrap_to, copy_subdirs=True, exclude=[]):
    """
    Create a data_vault connection to the LabRAD manager on one machine
    and copy data from a specified path.
    Recreate the copied data using another data_vault connection 
    to a different(or the same) manager at another specified path.
    
    wrap_from:
        a tuple wrapping the host machine and data_vault path to copy data from
        e.g. ('localhost',['','LabMember','Folder','Subfolder'])
        e.g. ('Hercules',['','Labmember','Folder'])
        
    wrap_to:
        a tuple wrapping the host machine and data_vault path to copy data to
    
    copy_subirs: 
        copy the whole directory structure, or just the datasets?
        if false, only the datasets are copied, and subdirectories are ignored.
        
    exclude:
        a list of subdirectories and/or datasets to exclude from the operation.
        e.g. exclude = 
        ['Subdirectory_1','00001 - Title of dataset','00002 - Another dataset']
    """

    # unwrap input arguments to machine names and directory paths
    [machine_from, path_from] = wrap_from
    [machine_to, path_to] = wrap_to 
    
    try:
        with labrad.connect(machine_from) as manager_from:
            try:
                dv_from = manager_from.data_vault
            except NotFoundError: # can't connect to dv_from
                print('Unable to connect to data_vault through LabRAD manager on' + 
                str(machine_from) + '.')
                print("Check that the data_vault is running and connected to the manager")
                return
                
            try:
                with labrad.connect(machine_to) as manager_to:
                    try:
                        dv_to = manager_to.data_vault
                    except NotFoundError: # can't connect to dv_to
                        print('Unable to connect to data_vault through LabRAD manager on' + 
                        str(machine_to) + '.')
                        print('Check that the data_vault is running and connected to the manager')
                        return
                        
                    # navigate to source
                    current_source_directory = navigate(dv_from, path_from)
                    if not current_source_directory == path_from:
                        print "Source directory '" + str(path_from) + "' not found."
                        print "..."
                        print "Copy operation aborted"
                        return dv_from
                    
                    # navigate to destination
                    current_dest_directory = navigate(dv_to, path_to)
                    if not current_dest_directory == path_to:
                        print "Destination directory '" + str(path_to) + "' not found."
                        if query_yes_no("Would you like to create it?"):
                            print "..."
                            navigate(dv_to, path_to, write=True)
                        else:
                            print "..."
                            print "Copy operation aborted."
                            return
                                           
                    if copy_subdirs:
                        """
                        out = {
                        num_datasets_present
                        num_datasets_included
                        num_datasets_created
                        num_subdirs_present
                        num_subdirs_included
                        num_subdirs_created}
                        """
                        out = copy_tree(dv_from, dv_to, write=False, exclude=exclude)
                        print("Ready to copy " + str(out[1]) + " of " + str(out[0]) + " datasets")
                        print("including " + str(out[4]) + " of " + str(out[3]) + " subdirectories")
                        print("from " + str(path_from) + " via machine '" + str(machine_from) + "'")
                        print("to " + str(path_to) + " via machine '" + str(machine_to) + "'.")
                        print(str(out[5]) + " directories will need to be created.")
                        print ""
                        if query_yes_no("Would you like to continue?"):
                            print "..."
                            out = copy_tree(dv_from, dv_to, exclude=exclude)
                            print "Created " + str(out[5]) + " new subdirectories."
                            print "Created " + str(out[2]) + " new datasets."
                            return
                        else:
                            print "..."
                            print "Copy operation aborted."
                            return
                        
                    else:
                        """
                        out = {
                        num_datasets_present
                        num_datasets_included
                        num_datasets_created}
                        """
                        out = recreate_datasets(dv_from, dv_to, write=False, exclude=exclude)
                        print("Ready to copy" + str(out[1]) + " of " + str(out[0]) + " datasets ")
                        print("from " + str(path_from) + " via machine '" + str(machine_from))
                        print("to " + str(path_to) + " via machine '" + str(machine_to) + "'.")
                        print("")
                        if query_yes_no("Would you like to continue?"):
                            print "..."
                            out = recreate_datasets(dv_from, dv_to, exclude=exclude)
                            print "Created " + str(out[2]) + " new datasets."
                            return
                        else:
                            print "..."
                            print "Copy operation aborted."
                            return
            
            except TypeError: # can't connect to machine_to
                print('Unable to connect to LabRAD manager on "' + 
                str(machine_to) + '".\nCheck that we are on the LabRAD whitelist for "' + 
                str(machine_to) + '".')
                return
    
    except TypeError: # can't connect to machine_from
        print('Unable to connect to LabRAD manager on "' + 
        str(machine_from) + '".\nCheck that we are on the LabRAD whitelist for "' + 
        str(machine_from) + '".')
        return
