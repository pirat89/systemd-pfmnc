#!/bin/python2


import re, argparse, sys
from os import listdir, path, mkdir, access, stat, W_OK, R_OK
from subprocess import call
from pprint import pprint

BASIC_DIR="/var/log/sd-test"
max_test=0;

#####################################################################
def get_params():
    """ Get and parse commandline parameters. """
    parser = argparse.ArgumentParser(
        prog="systemd-pfmnc-graph.py",
        description="""Script create summary files from logs of tests
                     of systestemd and graphs with gnuplot.""")
    parser.add_argument("-o","--output-dir", nargs=1,metavar="DIR",
        dest="output_dir", default=BASIC_DIR,
        help="path to output directory")
    parser.add_argument("-i","--input-dir", nargs=1,metavar="DIR",
        dest="input_dir", default=BASIC_DIR,
        help="""path to basic directory of systemd tests directory
              (default: """+BASIC_DIR+")")
    parser.add_argument("-l","--last", nargs=1,metavar="N", 
        dest="max_count", default=0, type=int,
        help="Plot last N tests (systemd versions). Default 0 (all).")
    parser.add_argument("--ignore-version", 
        dest="ignore_version", action="store_true", default=False,
        help="""If exists more tests for one version of systemd, 
              print them all. Default print only last.""")
    parser.add_argument("--graph-size", nargs=1,metavar="WIDTHxHEIGHT",
        dest="dimensions", default="800x600",
        help="dimensions of output graph - e.g. 1024x768 (default 800x600")
    parser.add_argument("--no-graph", dest="graph_enabled",
        action="store_false", default=True,
        help="Create only summary files without graphs.")
    parser.add_argument("--average", dest="average_enabled", 
        action="store_true", default=False,
        help="""calculate harmonic average for same tests of same versions
                of systemd""")
    parser.add_argument("--one-in", nargs=1, metavar="N", dest="one_in",
        type=int,
        default=1, help="Print every N test (or version/commit).")
    parser.add_argument("--auto-width", dest="auto_flag",
        default=False, action="store_true",
        help="""Automatically increase width if count of columns
                is unreadable for given size. However max allowed size
                is 4096px.""")
    parser.add_argument("-t", "--type", dest="type", metavar="TYPE",
        choices=['kernel','initrd','userspace','total'], default="total",
        help="""created graphs contains values from column kernel, initrd,
              userspace or their sum (total). This affects only sets of more
              then one test type (e.g. "1,2"). Alone graph contain all information. 
              Default: 'total'""")
    parser.add_argument("-c","--collections", nargs=1, metavar="RECIPE",
        dest="collections", default="A",
        help="""0,1,2   -> print results from tests 0,1,2 into one grap
                1 2     -> print tests 1,2 each in own graphs ----------
                1,2 1 3 -> combination -----------------------------
                Special char \"A\" - all tests into one graph --------
                e.g.: 1,3 1 A -> correct ---------------------------
                However you can't create tuple with A and other tests
                e.g.: 1,A,2 -> incorrect ---------------------------
                And special char \"X\" -> each test alone ------------
                for tests 1 - N generates: 1 2 .. N ----------------
                Default: "A" (everything give as one string!)""")

    params = parser.parse_args()
    params.max_count = get_int(params.max_count)
    params.one_in = get_int(params.one_in)
    params.collections = get_string(params.collections)
    
    if(re.match("^(((([0-9],)*[0-9])*( |$))*|((A|X)( |$)))*$", 
                params.collections) == None):
        parser.print_help()
        sys.exit(1)
    return params

#####################################################################
def get_int(tmp):
    if (isinstance(tmp, list)):
        if (isinstance(tmp[0],str)):
            return int(tmp[0])
        return tmp[0]
    if (isinstance(tmp,str)):
        return int(tmp)
    return tmp

def get_string(tmp_var):
    if(isinstance(tmp_var, list)):
        return "".join(tmp_var)
    return tmp_var

#####################################################################
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

#####################################################################
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

#####################################################################
def timesortedls(path_dir, reverse_flag=False):
    """ Return list of dirs/files in directory sorted 
        by mktime (youngest -> oldest) - or reverse if is set 2nd arg.
        Items with same timstamps are sorted by length of filename and
        filename"""
    mktime=lambda f: (stat(path.join(path_dir,f)).st_mtime,len(f),f)
    return sorted(listdir(path_dir), key=mktime, reverse=reverse_flag)

#####################################################################
def create_testList(path_dir):
    """ Get data from N_time files in current directory. """
    testList=[] 
    global max_test

    for dstfile in timesortedls(path_dir):
        if(re.match("[0-9]+_time",dstfile) == None): # change for test types
            continue
        test_type,log_type = dstfile.split("_")
        test_type = int(test_type)
        if(log_type != "time"): # redundant
            continue

        # get test type count
        # ----- !!ATTENTION!! -------
        # correct order is required!!!
        if(test_type > max_test):
            max_test = test_type

        # if some file missing (test type from 0 to N)
        while(test_type > len(testList)):
            testList.append(None)

        handle = open(path_dir+'/'+dstfile, "r")
        o = parsetime(handle.read().strip())
        testList.append(o)
        handle.close()
    return testList

#####################################################################
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
            i += 10


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

#####################################################################
def is_one_in(one_in):
    if(one_in < 1): # ignore non-sense values and se default
        one_in = 1
    counter = one_in;
    while(True):
        if(counter == one_in):
            counter = 0
            yield True
        else:
            yield False
        counter += 1

#####################################################################
def complete_summary_dict(sumdict):
    """ Add missing tests into the summary dict with default zero time values
        and replace "None" tests too. """
    global max_test
    default_dict = {"kernel" : 0, "initrd" : 0, "userspace" : 0}
    for version in sumdict.keys():
        for series in sumdict[version].keys():
            testList = sumdict[version][series]
            i = 0
            while (i < len(testList)):
                if (testList[i] == None):
                    testList[i] = default_dict
                i += 1
            i = max_test - len(testList)
            while (i > 0):
                testList.append(default_dict)
                i -= 1
            sumdict[version][series] = testList
    return sumdict

#####################################################################
def create_summary_dict(basic_dir,params):
    """ Create and return summary dict. Summary dict (sumdict) has ugly 
        structure:
        { sd_version : {series : [type_of_test { part_times }]}}
           commit ...
        """
    if(basic_dir[-1] != '/'):
        basic_dir += '/'

    counter=params.max_count
    one_in_gen = is_one_in(params.one_in)
    versionList= []
    sumdict={}
    for test_dir in timesortedls(basic_dir, True):
        if(path.isdir(basic_dir+test_dir) == False or
            re.match(".+?_[0-9]+",test_dir) == None): ### here TODO
            continue
        version,numero = test_dir.split("_")
        if((version in versionList) == False):
            versionList.insert(0,version)
            if(next(one_in_gen) == True):
                sumdict[version] = { int(numero): create_testList(basic_dir+test_dir) }
            else:
                continue
        elif(params.ignore_version == True):
            # must be here! not in prev condintion
            if(next(one_in_gen) == True):
                sumdict[version] [int(numero)] = create_testList(basic_dir+test_dir)
            else:
                continue
        elif(params.average_enabled == True):
            sumdict[version] [int(numero)] = create_testList(basic_dir+test_dir)
            continue
        else:
            continue

        counter -= 1
        if(counter == 0):
            break;
    
    sumdict = complete_summary_dict(sumdict)
    if(params.average_enabled == True):
        sumdict = calc_harmony_average(sumdict)
    return sumdict


#####################################################################
def create_graph(data_file,output_file,y_col,dimensions="800,600"):
    """ Create graph in SVG format from values in data_file. Ouput store 
        into the output_file."""
    y_col = str(y_col)

    gpcomlist = [
        "set style data linespoint",
        "set ylabel \"time [s]\"",
        "set xlabel \"systemd version\"",
        "set xtic rotate by 45 right",
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

#####################################################################
def create_graph_tests(data_dir,output_file,y_col,items,dimensions="800,600"):
    """ Create graph in SVG format from values in data_file. Ouput store 
        into the output_file."""

    y_col = str(y_col)
    fileList = [path.join(data_dir,"test_"+str(x)+".summary") for x in items]

    #for filename in timesortedls(data_dir):
    #    filepath = path.join(data_dir,filename)
    #    if(path.isdir(filepath) == True or
    #        re.match("^test_[0-9]\.summary",filename) == None):
    #        continue
    #    filelist.append(filepath)

    gpcomlist = [
        "set style data linespoint",
        "set ylabel \"time [s]\"",
        "set xlabel \"systemd version\"",
        "set xtic rotate by 45 right",
        "set style fill solid",
        "set xrange [] reverse",
        "set offset 0.5,0.5,0,0",
        "set grid ytics",
        "set terminal svg size "+ dimensions +" dynamic background rgb \"#ffffff\"",
        "set output \""+ output_file +"\"",
        ]

    plot_str="plot \""+ fileList[0] +"\" u "+ y_col
    plot_str +=":xticlabels(1) title \"test_"+str(items[0])+"\""

    i = 1
    while(i < len(fileList)):
        plot_str +=", \""+ fileList[i] +"\" u "+y_col+" title \"test_"+str(items[i])+"\""
        i += 1

    gpcomlist.append(plot_str)
    gpcomlist.append("set output") # flush hack
    call(["gnuplot","-e",";".join(gpcomlist)])

#####################################################################
def save_summary(sumdict,params):
    """ Create summary files for each type of test (0,1,2,..)"""
    head = "sd[_series]  kernel  initrd  userspace   total [sec]\n"
    line_format = "{:<14s}  {:7.3f} {:8.3f} {:11.3f}  {:8.3f}"
    df_list=[]

    # open all resume files and print header
    for i in range(max_test+1):
        handle = open(path.join(params.output_dir,"test_"+str(i)+".summary"), "w")
        handle.write(head)
        df_list.append(handle)

    # body
    # go through whole structure and print
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

#####################################################################
def print_graphs(params, count_items, count_tests):
    """Parse recipes for print of graphs  """

    def calc_dimensions(dimensions):
        if(re.match("[0-9]+x[0-9]+", dimensions)):
            dimensions = map(lambda x: int(x), dimensions.split("x"))
        else:
            dimensions = [800,600]
        if(params.auto_flag == True and dimensions[0] / count_items < 20):
            dimensions[0] = count_items * 20
            if(dimensions[0] > 4096):
                dimensions[0] = 4096
        return ",".join(map(lambda x: str(x),dimensions))


    choices={'kernel': 1, 'initrd': 2, 'userspace': 3, 'total': 4}
    collections = [list(set(i.split(","))) for i in params.collections.split(" ")]

    if(["X"] in collections):
        collections = [x for x in collections if x != ["X"]]
        collections += [[str(i)] for i in range(count_tests)]

    if(["A"] in collections):
        collections = [x for x in collections if x != ["A"]]
        collections.append([str(i) for i in range(count_tests)])

    # now unification and transformation str to int
    collections = [ map (lambda z: int(z),y.split(","))
                      for y in list(set([",".join(x) for x in collections]))]
    collections.sort(key=lambda x: (len(x),x[0]))
    
    #check max test
    _max = max([max(x) for x in collections])
    if( _max >= count_tests):
        sys.stderr.write("print_graphs(): You want to print test '"+
        str(_max)+"' which not exists!\n")
        exit(3)

    dim_str = calc_dimensions(params.dimensions)

    for item in collections:
        label = "-".join(map(lambda x: str(x), item))
        create_graph_tests(params.output_dir, 
                           path.join(params.output_dir,"graph_"+label+".svg"),
                           4,item,dim_str)

#####################################################################
######################### ===== MAIN ==== ###########################
#####################################################################
params = get_params()
params.output_dir = get_string(params.output_dir)
params.input_dir = get_string(params.input_dir)

if(check_dir(params.output_dir, W_OK) == False or
    check_dir(params.output_dir, R_OK) == False):
    exit(2)
if(check_dir(params.input_dir, R_OK) == False):
    exit(2)

sumdict = create_summary_dict(params.input_dir, params)
save_summary(sumdict,params)

if(params.graph_enabled == True):
    print_graphs(params, len(sumdict), max_test+1)
    #create_graph(
    #    path.join(params.output_dir,"test_2.summary"),
    #    path.join(params.output_dir,"uspace_2.svg"),
    #    4)
    #create_graph_all_tests(params.output_dir,path.join(params.output_dir,"uspace_all.svg"),4)

