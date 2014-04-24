#!/usr/bin/python3

import sys, argparse, socket, re
from socket import SOCK_STREAM, AF_INET, SHUT_RDWR, SOL_SOCKET, SO_REUSEADDR
from os import path
from subprocess import call
import pprint

HOST_PORT=4500
HOST_IP="127.0.0.1"
IP="127.0.0.1"
PORT=4501
SSH_LOGIN="pepek"


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

def check_str(tmp):
    if(isinstance(tmp,list)):
        return tmp[0]
    return tmp

def get_params():
    """ Get and parse commandline parameters. """
    parser = argparse.ArgumentParser(
        prog="sd-pfmnc-server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Network communication with \"tester machine\" (alias tester).
Possible are 2 modes:
  RQ_TEST 
        New test requested and FILE with data will be sended to tester.
        Return values:
            0      - success
            1      - some unexpected error
            2      - wrong commandline parameters
            3      - FILE not exists
            4      - connection failure
            5      - no patch - tester doesn't have code
            6      - file transmisstion failure
            7      - my protocol mismatch
            N > 7  - 
  RECV_RESULT
        Receiving of results expected. Received result is stored into FILE.
        File is tar archive!
        Return values:
            0      - success and passed tests
            2      - wrong commandline parameters
            4      - communication failure
            5      - result code is nonsense! probably commmunication error
            6      - file transmission failure
            7      - my protocol mismatch
            N > 7  - success but FAILED tests (7+test result), see tester.sh
    """
    )

    parser.add_argument("mode", metavar="MODE",
        choices=['RQ_TEST', 'RECV_RESULT'],
        help="RQ_TEST | RECV_RESULT")
    parser.add_argument("file", metavar="FILE",
        help="File for sending or storing - absolute path is recommended!")
    parser.add_argument("--patch",dest="patch_flag",
        action="store_true",default=False,
        help="""Sended file will be marked as git-patch which test machine
                apply on previous data but test machine must have complete
                source code of systemd.""")
    parser.add_argument("--host", nargs=2,
        metavar=("IP","PORT"), dest="host",default=[HOST_IP,HOST_PORT],
        help="""Set IP and PORT of host for connection.
                Default """+HOST_IP+" "+str(HOST_PORT))
    parser.add_argument("--bind", nargs=2,
        metavar=("IP","PORT"), dest="conn",default=[IP,PORT],
        help="""Set IP and PORT for binding when listen.
             Default """+IP+" "+str(PORT))
    parser.add_argument("--login",nargs=1, dest="login", 
        default=SSH_LOGIN, metavar="USER",
        help="""Set remote USER for file transmission by 'scp'. Default """+SSH_LOGIN)
    params = parser.parse_args()

    params.host = ipport(params.host)
    params.conn = ipport(params.conn)
    params.login = check_str(params.login)
    return params


def check_file(o_file):
    """ Check if file exists and is type file. Return True on success. """
    if(path.exists(o_file)):
        if(path.isfile(o_file)):
            return True
    print("File not exists or it's not file type!", file=sys.stderr)
    return False

def rq_test(src_file, conn,ssh_login, patch_flag):
    """ """
    if(check_file(src_file) == False):
        return 3
    if(patch_flag):
        msg = "NEWTEST PATCH "+str(128)
    else:
        msg = "NEWTEST CODE "+str(128)

    try:
        s = socket.socket(AF_INET, SOCK_STREAM)
        s.connect(tuple(conn))

        s.sendall(str.encode(msg))
        data = s.recv(512).decode()
        if(data[0:3] == "ACK"):
            dst_file = data[4:]
            retcode = call(["scp",src_file,ssh_login+"@"+conn[0]+":"+dst_file])
            if(retcode != 0):
                s.sendall("NACK")
                s.close()
                return 6
            s.sendall(b"ACK") # scp
        elif(data[0:6] == "NOCODE"):
            s.close()
            return 5
        else:
            print(data)
            s.close()
            return 7
    except ValueError:
        s.close()
        return 4

    s.close()
    return 0

def recv_result(o_file, conn):
    """ """
    tcode = 0
    msg = "ACK "+o_file
    try:
        ss = socket.socket(AF_INET, SOCK_STREAM)
        ss.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        ss.bind(tuple(conn))
        ss.listen(1)
    except ValueError:
        ss.close()
        return 4

    try:
        s, addr = ss.accept()
        data = s.recv(10).decode()
        if(data[0:3] == "ACK"):
            tcode = int(data[4:])
            if(tcode < 0):
                s.close()
                return 5
            elif(tcode > 0):
                tcode += 8
        s.sendall(str.encode(msg))
        data = s.recv(4).decode() # file transmission
        if(data == "ACK"):
            s.close()
            return tcode
    except ValueError:
        s.close()
        return 5
    except ValueError:
        ss.close()
        s.close()
        return 4 # communication failure
    ss.close()
    s.close()
    return 6

############################ MAIN ############################################
params = get_params()

if(params.mode == "RQ_TEST"):
    exit(rq_test(params.file,params.host, params.login, params.patch_flag))
else:
    exit(recv_result(params.file,params.conn))

