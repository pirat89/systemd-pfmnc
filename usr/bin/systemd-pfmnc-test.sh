#!/bin/bash

FLAG_NEW=0
REBOOT_ENABLED=1
STEP=-1
ROOTDIR=""
REBOOT_OS=""

if [[ $EUID -ne 0  ]]; then
  echo "This script must be run as root" 1>&2
 # exit 2
fi

print_usage() {
  echo "systemd-pfmnc-test.sh [ROOTDIR DIR] [next-reboot OS] [no-reboot] [new-test [N]]

  ROOTDIR  DIR    set \$ROOTDIR to DIR
                  this parameter is usefull when you want init tests from
                  else OS 
  next-reboot OS  set OS for reboots during testing (grub2-reboot OS)
                  last reboot after testing is to default system
  no-reboot       system must be rebooted manually - has effect only before
                  testing (ie. when 'new-test' is set)
  new-test [N]    Start new testing [from test number N]
"
}

test_arg() {
 if [[ $1 == "" ]]; then
   print_usage
   exit 1
 fi
}

#read some arguments
while [[ $1 != "" ]]; do
 param=$(echo $1 | sed -r "s/^(.*)=.*/\1/")

 if [[ "$param" != "$1"  ]]; then
    _VAL=$(echo $1 | sed -r "s/^.*=(.*)/\1/g");
    _USED_NEXT=0
 else
    _VAL="$2"
    _USED_NEXT=1
 fi

 case $param in
   ROOTDIR | --ROOTDIR)
     test_arg $_VAL
     ROOTDIR=$_VAL
     shift $_USED_NEXT
     ;;
   --new-test | new-test)
     FLAG_NEW=true
     if [[ $_VAL =~ ^[0-9][0-9]*$ ]]; then
       STEP=$[ $_VAL-1 ]
       shift $_USED_NEXT
     fi
     ;;
   --no-reboot | no-reboot)
     REBOOT_ENABLED=false
     ;;
   --next-reboot | next-reboot)
     test_arg $_VAL
     REBOOT_OS=$_VAL
     shift $_USED_NEXT
     ;;
   --help | -h)
     print_usage
     exit 0;
     ;;
   *)
     ;;
 esac
 shift
done

#erase "/" from end of *DIR
ROOTDIR=$(echo $ROOTDIR | sed "s/\/*$//")

#read basic directories
BDIR="$ROOTDIR/usr/bin"
WORK_DIR="$ROOTDIR/var/log/sysd-test"
JOURNAL_DIR="$ROOTDIR/var/log/journal"
TEST_DIR="$ROOTDIR/usr/lib/systemd/system"
DEF_PATH="$ROOTDIR/etc/systemd/system/default.target"
TEST_SERVICE_PATH="$ROOTDIR/etc/systemd/system/default.target.wants/sysd-performance-testing.service"
END_TEST=$(ls $TEST_DIR | grep -E "test_[0-9]+\.target$" | wc -l)
DATE=$(date +%Y_%m_%d)
SYSD_VERSION=$($BDIR/systemctl --version | head -1 | cut -d " " -f 2)
LOG_ENABLED=1

if [ ! -d $WORK_DIR ]; then
  echo "Create directory ${WORK_DIR}"
  mkdir -p $WORK_DIR
fi

# start new tests
if [[ $FLAG_NEW == true ]]; then
  if [[ $END_TEST -le 0 ]]; then
    echo "Tests not found!" >&2
    echo "Check if exists tests in forma 'test_N.target' with" >&2
    echo "'test_N.target.wants/' directory in $ROOTDIR/usr/lib/systemd/system/" >&2
    exit 1
  fi

  if [[ $STEP -ge $END_TEST ]]; then
    echo "You have only $END_TEST test. Chose lesser number for start" >&2
    exit 1
  fi

  LOG_ENABLED=0
  LAST=${SYSD_VERSION}_$(ls $WORK_DIR | grep ${SYSD_VERSION}_ | wc -l)
  rm -f $WORK_DIR/last
  mkdir $WORK_DIR/$LAST
  ln -s $LAST $WORK_DIR/last

  #init next reboot
  echo $REBOOT_OS > ${WORK_DIR}/reboot_OS_label
  
  # for more precision forbid fsck and NetworkManager\-wait\-online services
  systemctl list-units --full | grep -E "*NetworkManager\-wait\-online*" | cut -d " " -f 1 >  ${WORK_DIR}/masked_services
  cp $ROOTDIR/etc/fstab ${WORK_DIR}/my_fstab

  #TODO: rewrite to "manual" mask - for next OS -- check functionality -- in case that $ROOTDIR is set: masked_services from systemctl it's not always right solution
  for item in $(cat ${WORK_DIR}/masked_services); do 
    systemctl mask $item;
    ln -s /dev/null $ROOTDIR/etc/systemd/system/$item
  done
  cat ${WORK_DIR}/my_fstab | sed -r "s/\s*#.*$//g" | sed -r "s/[0-9]+$/0/g" > $ROOTDIR/etc/fstab

  if [[ ! -e $TEST_SERVICE_PATH ]]; then
    little_ugly_hack=$(echo $BDIR | sed "s/^$ROOTDIR//")
    echo -e "[Unit]\nDescription=Performance testing of systemd\nRequires=default.target\nAfter=default.target" \
            "\n\n[Service]\nType=idle\nExecStart=${little_ugly_hack}/systemd-pfmnc-test.sh\n\n" \
            "[Install]\nWanted=default.target\n" \
            > $TEST_SERVICE_PATH
  fi
elif [ -f ${WORK_DIR}/step ]; then
  STEP=$(cat ${WORK_DIR}/step)
  if [ $STEP -gt $END_TEST ]; then
    # testing ended
    echo "Testing already ended. For new testing try \"systemd-pfmnc-test.sh new-test\""
    exit
  fi
  REBOOT_OS=$(cat ${WORK_DIR}/reboot_OS_label)
else
  echo "Nothing to do. For new testing run \"systemd-pfmnc-test.sh new-test\""
  exit
fi


# save logs
if [ $LOG_ENABLED -eq 1 ]; then
 LOG_DIR=$WORK_DIR/last
 # LOG_DIR=`ls -d --sort=time $WORK_DIR/2* | head -1`

  # sometimes bootup is not yet finished
  COUNTER=50 
  
  systemd-analyze > $LOG_DIR/${STEP}_time 2>> $WORK_DIR/log_dir
  while [[ $? -ne 0 && $COUNTER -gt 0  ]]; do
    sleep 6;
    COUNTER=$[ $COUNTER-1 ]
    systemd-analyze > $LOG_DIR/${STEP}_time 2>> $WORK_DIR/log_dir
  done

  systemd-analyze blame > $LOG_DIR/${STEP}_blame 2>> $WORK_DIR/log_dir
  systemd-analyze critical-chain > $LOG_DIR/${STEP}_chain 2>> $WORK_DIR/log_dir
  systemd-analyze plot > $LOG_DIR/${STEP}_graph.svg 2>> $WORK_DIR/log_dir
fi

#prepare next test
STEP=$[ $STEP+1 ]
echo $STEP > ${WORK_DIR}/step

# clean journal
#TODO: add option for storing of journal before removing
rm -rf $JOURNAL_DIR/*

if [ $STEP -lt $END_TEST ]; then
 rm -f $DEF_PATH 
 ln -s $ROOTDIR/lib/systemd/system/test_${STEP}.target $DEF_PATH
 if [[ $REBOOT_OS != ""  ]]; then grub2-reboot "$REBOOT_OS"; fi
 if [[ $REBOOT_ENABLED -eq 1 ]]; then
   reboot
 else
   echo "You set parameter '--no-reboot'. Test begin after you"
   echo "reboot manually. Please remember that some critical changes"
   echo "have been made! (e.g. in fstab, systemctl). Restore option is not"
   echo "implemented yet."
 fi
elif [ $STEP -eq $END_TEST ]; then
  rm -f $DEF_PATH
  ln -s $ROOTDIR/usr/lib/systemd/system/graphical.target $DEF_PATH
  if [[ $REBOOT_OS != ""  ]]; then grub2-reboot "$REBOOT_OS"; fi
  reboot
else
  # creat summary files and graphs
  $BDIR/systemd-pfmnc-graph.py -i $WORK_DIR -o $WORK_DIR

  # finish clean after test
  mv -f ${WORK_DIR}/my_fstab $ROOTDIR/etc/fstab
  for i in $(cat ${WORK_DIR}/masked_services); do systemctl unmask $i; done
  rm ${WORK_DIR}/masked_services
  rm -f $TEST_SERVICE_PATH

  
  # after remove is problem with SELinux and systemd-analyze for this boot
  # so do last reboot
  reboot
fi

