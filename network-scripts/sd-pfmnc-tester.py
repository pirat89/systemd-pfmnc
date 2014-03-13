#!/usr/bin/python3

import sys, socket, argparse, re
from socket import SOCK_STREAM, AF_INET, SHUT_RDWR, SOL_SOCKET, SO_REUSEADDR
from os import path
from subprocess import call
import pprint

HOST_PORT=4501
HOST_IP="127.0.0.1"
IP="127.0.0.1"
PORT=4500
SSH_LOGIN="pepek" # used for file transmission by scp

########################## FUNCTIONS #########################################
def ipport(tmpList):
    try:
        i = int(tmpList[1])
        if(i > 65535 or i < 0):
            print("port must be in range 0 - 65535",file=sys.stderr)
            exit(2)
    except:
        print("port must be integer",file=sys.stderr)
        exit(2)
    return [tmpList[0],i]

def check_int(i):
    if(isinstance(i,list)):
        return i[0]
    return i

def get_params():
    """ Get and parse commandline parameters. """
    parser = argparse.ArgumentParser(
        prog="sd-pfmnc-server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Network communication with \"server machine\" (alias server).
Possible are 2 modes:
  RECV_TRQ 
        New test requested and FILE with data will be received.
        Return values:
            0      - success - received source code
            1      - some unexpected error
            2      - wrong commandline parameters
            3      - FILE not exists
            4      - communication failure
            5      - no patch - source code did not be received yet
            6      - file transmission failure
            7      - my protocol mismatch
            8      - success received patch
  SEND_RESULT
        Receiving of results expected. Received result is stored into FILE.
        File is tar archive!
        Return values:
            0      - success
            1      - some unexpected error
            2      - wrong commandline parameters
            4      - communication failure
            6      - file transmission failure
            7      - my protocol mismatch
    """
    )

    parser.add_argument("mode", metavar="MODE",
        choices=['RECV_TRQ', 'SEND_RESULT'],
        help="RECV_TRQ | SEND_RESULT")
    parser.add_argument("file", metavar="FILE",
        help="File for sending absolute path is recommended! For storing is recommended relative path - trasmission by scp to non-privileged user")
    parser.add_argument("--patch",dest="patch_flag",
        action="store_true",default=False,
        help="Source code exists on machine. Patch is allowed.")
    parser.add_argument("--host", nargs=2,
        metavar=("IP","PORT"), dest="host",default=[HOST_IP,HOST_PORT],
        help="""Set IP and PORT of host for connection.
             Default """+HOST_IP+" "+str(HOST_PORT))
    parser.add_argument("--bind", nargs=2,
        metavar=("IP","PORT"), dest="conn",default=[IP,PORT],
        help="""Set IP and PORT for binding when listen.
             Default """+IP+" "+str(PORT))
    parser.add_argument("--test-result", nargs=1, type=int, dest="tcode",
        metavar="N", default=0,
        help="result of testing (0..N). Default 0");
    parser.add_argument("--login", nargs=1, dest="login", 
        metavar="USER", default=SSH_LOGIN,
        help="""Set remote USER for file trasmission by 'scp'.
                Default """+SSH_LOGIN)
    params = parser.parse_args()

    params.host = ipport(params.host)
    params.conn = ipport(params.conn)
    params.tcode = check_int(params.tcode)
    
    return params


def check_file(o_file):
    """ Check if file exists and is type file. Return True on success. """
    if(path.exists(o_file)):
        if(path.isfile(o_file)):
            return True
    print("File not exists or it's not file type!", file=sys.stderr)
    return False

def recv_trq(o_file, conn, patch_flag):
    ack_path = "ACK "+o_file
    file_type_return = 0
    try:
        ss = socket.socket(AF_INET, SOCK_STREAM)
        ss.setsockopt(SOL_SOCKET, SO_REUSEADDR,1)
        ss.bind(tuple(conn))
        ss.listen(1)
    except ValueError:
        ss.close()
        return 4
    try:
        s, addr = ss.accept()
        data = s.recv(32).decode()
        print(data[8:13])
        if(data[0:7] != "NEWTEST"): # mismatch
            print(data)
            s.close()
            ss.close()
            return 7

        if(data[8:13] == "PATCH"):
            if(patch_flag == False):
                s.sendall(b"NOCODE")
                s.close()
                ss.close()
                return 5
            file_type_return = 8
        elif(data[8:12] != "CODE"): # mismatch
            print("data: "+data)
            s.close()
            ss.close()
            return 7

        s.sendall(str.encode(ack_path))
        data = s.recv(4).decode()
        s.close()
        ss.close()
        if(data == "ACK"):
            return file_type_return  # success
    except ValueError:
        print("failure")
        ss.close()
        s.close()
        return 4
    return 6 # file transmission failure

def send_result(src_file, conn, ssh_login, tcode):
    if(check_file(src_file) == False):
        return 3
    msg = "RESULTS "+str(tcode)
    try:
        s = socket.socket(AF_INET, SOCK_STREAM)
        s.connect(tuple(conn))
        s.sendall(str.encode(msg))
        data = s.recv(512).decode()

        if(data[0:3] == "ACK"):
            dst_file = data[4:]
            if(len(dst_file) == 0):
                s.close()
                return 7 # mismatch - empty path
        else:
            s.close()
            return 7
        # file transmission
        retcode = call(["scp",src_file,ssh_login+"@"+conn[0]+":"+dst_file])
        if(retcode != 0):
            s.close()
            return 6
        s.send(b"ACK")
    except ValueError:
        s.close()
        return 4
    s.close()
    return 0
############################ MAIN ############################################
params = get_params()
pprint.pprint(params)

if(params.mode == "RECV_TRQ"):
    exit(recv_trq(params.file, params.conn, params.patch_flag))
else:
    exit(send_result(params.file,params.host, params.login, params.tcode))
