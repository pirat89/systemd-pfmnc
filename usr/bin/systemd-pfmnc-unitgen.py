#!/bin/python

import sys
from os import path, access,stat, W_OK, R_OK

def print_usage():
  print("""Descripttion:
       Script generate N units (services) in format test_[0-9]+.service
       with dependencies (weight-balanced binary tree).
        """)
    print("Usage:\n    systemd-pfmnc-unitgen.py O_DIR N")
    print("       O_DIR   output directory")
    print("       N       number of units")

def getparams():
    if(len(sys.argv) != 3):
        print_usage()
        sys.exit(1)

    if(sys.argv[2].isdigit() == False):
        print_usage()
        sys.exit(1)

    return sys.argv[1], int(sys.argv[2])

def check_dir(o_dir, mode):
    """ Check if o_dir exists and it is directory with read/write
        permission. Return False on error."""
    if(path.exists(o_dir)):
        if(path.isdir(o_dir)):
            if(access(o_dir,mode)):
                 return True
            else:
                msg="write" if(mode == W_OK) else "read"
                sys.stderr.write('"'+o_dir+'": no '+msg+' permission\n')
                return False
        else: 
            sys.stderr.write('"'+o_dir+'": is not directory\n')
            return False

    sys.stderr.write('"'+o_dir+'": directory not exists\n')
    return False

def processNodes():
    """ create dependencies for work_nodeList
        Dependencies between units are weight-balanced binary tree.
        """
    # ugly globals, but it's more effective here
    global work_nodeList, processed_nodeList, listList
    global dependenciesList, next_unit
    from_end = False;
    item = None; 

    while(next_unit <= unit_count):
        if(len(work_nodeList) == 0):
            break
        if(from_end == False):
            # left half
            item = work_nodeList.pop(0)
            processed_nodeList.insert(0,item)
            listList.insert(0,next_unit)
        else:
            # right half
            item = work_nodeList.pop()
            processed_nodeList.append(item)
            listList.append(next_unit)

        dependenciesList[item].append(next_unit)
        next_unit += 1
        from_end ^= True

def write_prefix(handle):
    handle.write("[Unit]\n")
    handle.write("Description=Little service for testing\n")
    handle.write("DefaultDependencies=no\n")

def write_dependency(handle,itemList):
    tmp_str= ""

    for item in itemList:
        tmp_str += "test_"+str(item)+".service,"

    handle.write("Requires="+tmp_str[:-1]+"\n")
    handle.write("After="+tmp_str[:-1]+"\n")

def write_postfix(handle):
    handle.write("\n")
    handle.write("[Service]\n")
    handle.write("Type=simple\n")
    handle.write("ExecStart=/bin/echo \"test\"\n")

def create_units(dependenciesList, o_dir, unit_count):
    i = 1
    itemList = None

    while(i <= unit_count):
        handle = open(path.join(o_dir,"test_"+str(i)+".service"), "w")
        itemList = dependenciesList[i]

        write_prefix(handle)
        
        if(len(itemList) > 0):
            write_dependency(handle, itemList)

        write_postfix(handle)
        handle.close()
        i += 1

################################# MAIN #######################################

o_dir, unit_count = getparams();

if(check_dir(o_dir, W_OK) == False):
    sys.exit(2)

work_nodeList= [1];
processed_nodeList = [];
listList = [];
dependenciesList=[]
next_unit = 2;

i=0;
while(i <= unit_count):
  dependenciesList.insert(0,[])
  i +=1


while(True):
    processNodes()
    if(len(work_nodeList) > 0 or next_unit > unit_count):
        break

    work_nodeList, processed_nodeList = processed_nodeList, work_nodeList
    processNodes()
    if(len(work_nodeList) > 0 or next_unit > unit_count):
        break

    work_nodeList = listList
    listList = []
    processed_nodeList = []

create_units(dependenciesList, o_dir, unit_count)

