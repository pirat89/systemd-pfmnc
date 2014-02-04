#!/bin/python


import re, argparse, sys
from os import listdir, path, mkdir, access, stat, W_OK, R_OK
from subprocess import call

BASIC_DIR="/var/log/sd-test"
count_tests=2;

def getparams():
    """ Get and parse commandline parameters. """
    parser = argparse.ArgumentParser(
        prog="testresume",
        description="Script create summary files from logs of tests of systestemd and graphs with gnuplot.")
    parser.add_argument("-o","--output-dir", nargs=1,metavar="DIR",
        dest="output_dir", default=BASIC_DIR,
        help="path to output directory")
    parser.add_argument("-i","--input-dir", nargs=1,metavar="DIR",
        dest="input_dir", default=BASIC_DIR,
        help="path to basic directory of systemd tests directory (default: "+BASIC_DIR+")")
    parser.add_argument("-l","--last", nargs=1,metavar="N", 
        dest="max_count", default=0, 
        help="Plot last N tests (systemd versions). Default 0 (all).")
    parser.add_argument("--ignore-version", 
        dest="ignore_version", action="store_true", default=False,
        help="If exists more tests for one version of systemd, print them all. Default print only last.")
    parser.add_argument("--graph-size", nargs=1,metavar="WIDTHxHEIGHT",
        dest="dimensions", default="800x600",
        help="dimensions of output graph - e.g. 1024x768 (default 800x600")
    parser.add_argument("--no-graph", dest="graph_enabled",
        action="store_false", default=True,
        help="Create only summary files without graphs.")
    parser.add_argument("--average", dest="average_enabled", 
        action="store_true", default=False,
        help="calculate harmonic average for same tests of same versions of systemd")
    #parser.add_argument("", nargs="?",metavar="DIR", dest="", help="")
    
    return parser.parse_args()

def get_string(tmp_var):
    if( isinstance(tmp_var, list)):
        return "".join(tmp_var)
    return tmp_var

def check_dir(o_dir, mode):
    """ Check if o_dir exists, it is directory with read/write permission.
        If o_dir not exists it will be created.
        Return False on error."""
    if(path.exists(o_dir)):
        if(path.isdir(o_dir)):
            if(access(o_dir,mode)):
                 return True
            else:
                msg="write" if(mode == W_OK) else "read"
                sys.stderr.write('"'+o_dir+'": no '+msg+' permission')
                return False
        else: 
            sys.stderr.write('"'+o_dir+'": is not directory')
            return False
    else:
        try:
            mkdir(o_dir)
        except:
            sys.stderr.write(sys.exc_info()[0])
        return False

def parsetime(msg):
    """ Parse times from msg (output from 'systemd-analyze time').
        Return dict containing times of each part in msg or None."""
    re_time=re.compile("(?:(?:(?P<min>[0-9.]+)min )|(?:(?P<s>[0-9.]+)s )|(?:(P<ms>[0-9.]+)ms ))+\((?P<part>[a-z]+)\)")
    timedict={"kernel" : 0, "initrd" : 0, "userspace" : 0}
    wrong_format=True
    for item in re_time.finditer(msg):
        wrong_format=False
        itemdict=item.groupdict()
        if("min" in itemdict and itemdict["min"] != None):
            t=60*float(itemdict["min"])
        else:
            t=0
        if("s" in itemdict and itemdict["s"] != None):
            t+=float(itemdict["s"])
        elif("ms" in itemdict and itemdict["ms"] != None):
            t+=float(itemdict["ms"])/1000
        timedict[itemdict["part"]]=t
    return timedict if(wrong_format == False) else None

def timesortedls(path_dir, reverse_flag=False):
    """ Return list of dirs/files in directory sorted 
        by mktime (youngest -> oldest)."""
    mktime=lambda f: stat(path.join(path_dir,f)).st_mtime
    return sorted(listdir(path_dir), key=mktime, reverse=reverse_flag)

def create_testlist(path_dir):
    """ Get data from N_time files in current directory. """
    testlist=[] 
    global count_tests

    for dstfile in timesortedls(path_dir):
        test_type,log_type = dstfile.split("_")
        if(log_type != "time"):
            continue

        # get test type count
        if(int(test_type) > count_tests):
            count_tests = int(test_type)

        handle = open(path_dir+'/'+dstfile, "r")
        o = parsetime(handle.read().strip())
        print(o,dstfile)
        testlist.append(o)
        handle.close()
    return testlist

def calc_harmony_average(sumdict):
    """ Calculate harmonic average (mean) for tests of sd version.
        It's ugly, but it's possible division by zero. 
    """
    
    for version in sumdict.keys():
        tmpList = sumdict[version][0]
        num = len(sumdict[version])
        
        i=0
        while(i < len(tmpList)):
            if(tmpList[i]["kernel"] > 0): 
                tmpList[i]["kernel"]    = 1 / float(tmpList[i]["kernel"])
            if(tmpList[i]["initrd"] > 0): 
                tmpList[i]["initrd"]    = 1 / float(tmpList[i]["initrd"])
            if(tmpList[i]["userspace"] > 0): 
                tmpList[i]["userspace"] = 1 / float(tmpList[i]["userspace"])
            i += 1


        for serie in sumdict[version].keys():
            if(serie == 0):
                continue

            i=0
            while(i < len(tmpList)):
                if(sumdict[version][serie][i]["kernel"] > 0):
                    tmpList[i]["kernel"]    += 1 / float(sumdict[version][serie][i]["kernel"])
                if(sumdict[version][serie][i]["initrd"] > 0):
                    tmpList[i]["initrd"]    += 1 / float(sumdict[version][serie][i]["initrd"])
                if(sumdict[version][serie][i]["userspace"] > 0):
                    tmpList[i]["userspace"] += 1 / float(sumdict[version][serie][i]["userspace"])
                i += 1
        i=0
        while(i < len(tmpList)):
            if(tmpList[i]["kernel"] > 0):
                tmpList[i]["kernel"] = num / tmpList[i]["kernel"]
            if(tmpList[i]["initrd"] > 0):
                tmpList[i]["initrd"] = num / tmpList[i]["initrd"]
            if(tmpList[i]["userspace"] > 0):
                tmpList[i]["userspace"] = num / tmpList[i]["userspace"]
            i += 1
        sumdict[version] = { 0 : tmpList }
    return sumdict

def create_summary_dict(basic_dir,params):
    """ Create and return summary dict. Summary dict (sumdict) has ugly 
        structure:
        { sd_version : {series : [type_of_test { part_times }]}}
        """
    if(basic_dir[-1] != '/'):
        basic_dir += '/'
    counter=params.max_count
    sumdict={}
    for test_dir in timesortedls(basic_dir, True):
        if(path.isdir(basic_dir+test_dir) == False or
            re.match("[0-9]+_[0-9]+",test_dir) == None):
            continue
        version,numero = test_dir.split("_")
        if(sumdict.has_key(int(version)) == False):
            sumdict[int(version)] = { int(numero): create_testlist(basic_dir+test_dir) }
        elif(params.ignore_version == True):
            sumdict[int(version)] [int(numero)] = create_testlist(basic_dir+test_dir)
        elif(params.average_enabled == True):
            sumdict[int(version)] [int(numero)] = create_testlist(basic_dir+test_dir)
            continue
        else:
            continue

        counter -= 1
        if(counter == 0):
            break;

    if(params.average_enabled == True):
        sumdict = calc_harmony_average(sumdict)

        
    return sumdict


def create_graph(data_file,output_file,y_col,dimensions="800,600"):
    """ Create graph in SVG format from values in data_file. Ouput store 
        into the output_file."""
    if(re.match("[0-9]+x[0-9]+", dimensions)):
        dimensions=dimensions.replace("x",",")
    else:
        dimensions="800,600"
    y_col = str(y_col)

    gpcomlist = [
        "set style data linespoint",
        "set ylabel \"time [s]\"",
        "set xlabel \"systemd version\"",
        "set style fill solid",
        "set xrange [] reverse",
        "plot \""+ data_file +"\" u "+ y_col +":xticlabels(1) notitle",
        "set offset 0.5,0.5,GPVAL_Y_MAX/100*10,0",
        "set terminal svg size "+ dimensions +" dynamic background rgb \"#ffffff\"",
        "set output \""+ output_file +"\"",
        "plot \""+ data_file +"\" u "+ y_col +":xticlabels(1) notitle, \""+ data_file +"\" u ($0):"+ y_col +":(sprintf(\"%.2f\",$"+ y_col +")) with labels offset -0.5,1 notitle",
        "set output"
        ]
    call(["gnuplot","-e",";".join(gpcomlist)])

def create_graph_all_tests(data_dir,output_file,y_col,dimensions="800,600"):
    """ Create graph in SVG format from values in data_file. Ouput store 
        into the output_file."""
    if(re.match("[0-9]+x[0-9]+", dimensions)):
        dimensions=dimensions.replace("x",",")
    else:
        dimensions="800,600"
    y_col = str(y_col)
    filelist=[]

    for filename in timesortedls(data_dir):
        filepath = path.join(data_dir,filename)
        if(path.isdir(filepath) == True or
            re.match("^test_[0-9]\.summary",filename) == None):
            continue
        filelist.append(filepath)
    
    gpcomlist = [
        "set style data linespoint",
        "set ylabel \"time [s]\"",
        "set xlabel \"systemd version\"",
        "set style fill solid",
        "set xrange [] reverse",
        "set offset 0.5,0.5,0,0",
        "set grid ytics",
        "set terminal svg size "+ dimensions +" dynamic background rgb \"#ffffff\"",
        "set output \""+ output_file +"\"",
        "plot \""+ filelist[0] +"\" u "+ y_col +":xticlabels(1) title \"test_0\", \""+ filelist[1] +"\" u "+ y_col +" title \"test_1\", \""+ filelist[2] +"\" u "+ y_col +" title \"test_2\", \""+ filelist[3] +"\" u "+ y_col +" title \"test_3\"",
        "set output"
        ]
    call(["gnuplot","-e",";".join(gpcomlist)])

def save_summary(sumdict,params):
    """ Create summary files for each type of test (0,1,2,..)"""
    head = "sd[_series]  kernel  initrd  userspace   total [sec]\n"
    line_format = "{:<14s}  {:7.3f} {:8.3f} {:11.3f}  {:8.3f}"
    df_list=[]

    for i in range(count_tests+1):
        handle = open(path.join(params.output_dir,"test_"+str(i)+".summary"), "w")
        handle.write(head)
        df_list.append(handle)

    for sdv in sorted(sumdict.keys(), reverse=True):
        sd_dict = sumdict[sdv]
        for series in sorted(sd_dict.keys(), reverse=True):
            test_list = sd_dict[series]
            i = 0
            sd_str = str(sdv)
            if(params.ignore_version == True):
              sd_str += "_"+str(series)
            for test in test_list:
                df_list[i].write(line_format.format(sd_str,
                    test["kernel"],test["initrd"],test["userspace"],
                    test["kernel"]+test["initrd"]+test["userspace"])+"\n")
                i +=1
    
    for handle in df_list:
        handle.close()
    return 0

######################### ===== MAIN ==== ###################################
params = getparams()
params.output_dir = get_string(params.output_dir)
params.input_dir = get_string(params.input_dir)

if(check_dir(params.output_dir, W_OK) == False or
    check_dir(params.output_dir, R_OK) == False):
    exit(1)
if(check_dir(params.input_dir, R_OK) == False):
    exit(2)

sumdict = create_summary_dict(params.input_dir, params)
save_summary(sumdict,params)

if(params.graph_enabled == True):
    create_graph(
        path.join(params.input_dir,"test_2.summary"),
        path.join(params.output_dir,"uspace_2.svg"),
        4)
    create_graph_all_tests(params.input_dir,path.join(params.output_dir,"uspace_all.svg"),4)

