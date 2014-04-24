#!/bin/bash
#############################################################################
# YOU HAVE TO SET MANY PARAMETERS HERE!
# CHECK YOUR RULES FOR FIREWALL! THIS IS NOT CONFIGURATED AUTOMATICALLY
#############################################################################
SRC_DIR="/home/pirat/Downloads/systemd"
RECV_DIR="/home/pepek"
SEC_OS_DEV=/dev/sda6
SEC_OS_DIR="/mnt/test"
NSPAWN_MACHINE="/srv/test"
NSPAWN_MACHINE_BACKUP="/srv/test_backup"
LOG_DIR="/var/log/sd-test"

COUNTER=0
root_label="root00"
snapshot_label="backup"
performance_script="${SEC_OS_DIR}/${root_label}/usr/bin/systemd-pfmnc-test"
network_script="/usr/bin/sd-pfmnc-tester.py"
recv_file="test.tar.xz"
log_file="process.log"
SEC_OS_WORK_DIR="${SEC_OS_DIR}/$root_label/var/log/sd-test"

PATCH_PARAM=""
remote_user="fedora"

IP="192.168.10.10"
PORT="4500"
HOST_IP="192.168.10.20"
HOST_PORT="4501"

#check root
if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root" 1>&2
  exit 1
fi

##############################################################################
#                                FUNCTIONS                                   #
##############################################################################

#check return value - when $? is non-zero, exit
#TODO: with jenkins must be edited!
success_test() { if [[ $? -ne O ]]; then echo $1 1>&2; return 1; fi }

#TODO: jenkins communication - get new commits,etc....

##############################################################################
prepare_src() {
  echo "[NEXTSTEP] COPY SOURCE CODE OR APPLY PATCH"
  tar -Jxf $RECV_DIR/$recv_file -C $RECV_DIR
  origin_label=$(tar -tf $RECV_DIR/$recv_file | head -n 1) # patch file or systemd/
  # if patch do else other do fi
  if [[ $status -eq 8 ]]; then  # patch received
    cd $SRC_DIR
    git apply $RECV_DIR/$origin_label
    status=$?
    cd -
    rm -f $RECV_DIR/$origin_label
  else # complete source code received
    rm -rf $SRC_DIR
    mv $RECV_DIR/$origin_label $SRC_DIR
    status=$?
  fi  

  rm -rf $RECV_DIR/$recv_file
  return $status 
}

##############################################################################
sysd_compilation() {
  ## configure,compile, install into nspawn machine
  echo "[NEXTSTEP] SYSTEMD COMPILATION"
  cd $SRC_DIR
  make clean
  ./autogen.sh
  success_test "[FAILED] ${SRC_DIR}/autogen.sh" || { cd - && return 1; }
  
  ./configure CFLAGS='-g -O0 -ftrapv' --enable-kdbus --sysconfdir=/etc --localstatedir=/var --libdir=/usr/lib64 --enable-gtk-doc
  success_test "[FAILED] ${SRC_DIR}/configure" || { cd - && return 1; }

  make
  success_test "[FAILED] systemd compilation" || { cd - && return 1; }

  cd -
  return 0
}

##############################################################################
test_nspawn() {
  echo "[NEXTSTEP] NSPAWN TEST"
  cd $SRC_DIR
  make DESTDIR=$NSPAWN_MACHINE install
  success_test "[FAILED] make DESTDIR=$NSPAWN_MACHINE install" || { cd - && return 1; }
  cd -  

  #start test_machine
  #TODO: timeout or smthng smlr
  ### machinectl terminate test${COUNTER}
  
  TEST_STARTTIME=$(date +"%T")
  TIME_OUT=0
  #it's ugly but the only credible solution which I thought up
  (
    sleep 10 && if [[ $(machinectl list | tail) != ""  ]]; then
      machinectl terminate $(machinectl list | tail | cut -d " " -f 1);
      TIME_OUT=1
    fi 
  ) &
  time_guard_PID=$!
  systemd-nspawn -M test${COUNTER} -jbD $NSPAWN_MACHINE
  tmp_val=$?

  while [[ $tmp_val -eq 251 ]]; do
    kill -9 $time_guard_PID
    (
      sleep 10 && if [[ $(machinectl list | tail) != ""  ]]; then
        machinectl terminate $(machinectl list | tail | cut -d " " -f 1);
        TIME_OUT=1
      fi
    ) &
    time_guard_PID=$!
    COUNTER=$[ $COUNTER +1 ]
    systemd-nspawn -M test${COUNTER} -jbD $NSPAWN_MACHINE
    tmp_val=$?
  done

  if [[ $TIME_OUT -eq 1 ]]; then 
    echo "[FAILED] test nspawn timeout" >&2;
    return 1
  elif [[ $tmp_val -ne 0 ]]; then
    echo "[FAILED] test nspawn return value: $tmp_val" >&2
    return 1
  fi
  
  #test if "everything is OK" - here means if systemd reach last target
  #TODO: for now only minitest, add testing of failed services, e.g. LOGIND
  #journalctl -rm --since $TEST_STARTTIME _HOSTNAME=test${COUNTER} | grep -i "Startup finished in"
  #success_test "[FAILED] test nspawn machine did not boot correctly" >&2 || return 1

  return 0
}
  
##############################################################################
init_pfmnc_test() {
  echo "[NEXTSTEP] INIT PERFORMANCE TESTS"
  btrfs sub snap -r ${SEC_OS_DIR}/$root_label ${SEC_OS_DIR}/$snapshot_label
  
  #install new systemd into second OS
  cd ${SRC_DIR}
  make DESTDIR=${SEC_OS_DIR}/$root_label install
  cd -

  #TODO:tests init - when feature dynamic tests will be completed
  $performance_script --no-reboot --pre-dracut "initramfs-testing.img"  ROOTDIR=${SEC_OS_DIR}/$root_label --next-reboot "Linux testing" new-test
  success_test "[FAILED] performance tests init" || return 1

  return 0
}

##############################################################################
load_backup_snap() {
  #load origin snapshot
  btrfs sub del ${SEC_OS_DIR}/$root_label
  btrfs sub snap ${SEC_OS_DIR}/$snapshot_label ${SEC_OS_DIR}/$root_label
  btrfs sub del ${SEC_OS_DIR}/$snapshot_label
}

##############################################################################
new_test() {
  # new_test is the most important faunction here!
  if [[ -e $SRC_DIR ]]; then PATCH_PARAM="--patch"; fi

  $network_script $PATCH_PARAM --bind $IP $PORT RECV_TRQ $recv_file
  status=$?
  while [[ $status -ne 0 && $status -ne 8 ]]; do
    sleep 1
    $network_script $PATCH_PARAM --bind $IP $PORT RECV_TRQ $recv_file
    status=$?
  done
  prepare_src || return 1

  # fun begin
  sysd_compilation || return 2
  rm -rf $NSPAWN_MACHINE
  cp -r $NSPAWN_MACHINE_BACKUP $NSPAWN_MACHINE
  test_nspawn ||  return 3

  init_pfmnc_test || { load_backup_snap && return 4; }
  return 0
}

##############################################################################
#                             MAIN FUNCTION                                  #
##############################################################################
#check dir for mountpoint
if [[ ! -d $SEC_OS_DIR  ]]; then mkdir -p $SEC_OS_DIR; fi
if [[ ! -d $LOG_DIR ]]; then mkdir -p $LOG_DIR; fi
if [[ ! -d $SRC_DIR ]]; then mkdir -p $SRC_DIR; fi

#mount 2nd OS
mountpoint $SEC_OS_DIR >/dev/null 2>/dev/null
if [[ $? -ne 0 ]]; then
  mount -t btrfs $SEC_OS_DEV $SEC_OS_DIR
  success_test "[FAILED] can't mount dev with second OS $SEC_OS_DEV to $SEC_OS_DIR" || exit 1
fi


if [[ -e ${LOG_DIR}/check_pfmnc_test ]]; then
  # performance testing finished

  ##TODO: check results of pfmnc testing
  LAST_PATH="${SEC_OS_DIR}/${root_label}$( readlink $SEC_OS_WORK_DIR/last )"

  rm -rf $LOG_DIR/result
  rm -f $LOG_DIR/check_pfmnc_test
  echo "[NEXTSTEP-tmpdebug] get results" >> $LOG_DIR/$log_file 2>> $LOG_DIR/$log_file

  cp -r $LAST_PATH $LOG_DIR/result
  cp /boot/initramfs-testing.img.backup /boot/initramfs-testing.img
  load_backup_snap

  #TODO: put every other important file to result dir
  status=0
  cd $LOG_DIR
  mv $log_file result/$log_file

  tar -Jcf result.tar.xz result
  echo "odesilam"
  $network_script --host $HOST_IP $HOST_PORT --test-result $status --login $remote_user  SEND_RESULT $LOG_DIR/result.tar.xz # >> $log_file 2>> $log_file
  status2=$?
  echo "send: $status" >> $log_file
  if [[ $status2 -ne 0 ]]; then # last chance, server must listen..
    sleep 10
    $network_script --host $HOST_IP $HOST_PORT --test-result $status --login $remote_user  SEND_RESULT $LOG_DIR/result.tar.xz #  >> $log_file 2>> $log_file
  fi
  mv result.tar.xz result.tar.xz.backup
  cd -
fi

# new testing - new data
while [[ 1 ]]; do # while is used on error before reboot
  rm -f $LOG_DIR/$log_file
  new_test >> $LOG_DIR/$log_file 2>> $LOG_DIR/$log_file # the most important function
  status=$?
  if [[ $status -eq 0 ]];then
    touch ${LOG_DIR}/check_pfmnc_test
    reboot
    exit 0
  fi
  
  # error - send result
  cd $LOG_DIR
  mkdir result
  mv $log_file result/$log_file
  tar -Jcf result.tar.xz result

  $network_script --host $HOST_IP $HOST_PORT --test-result $status --login $remote_user   SEND_RESULT $LOG_DIR/result.tar.xz
  if [[ $? -ne 0 ]]; then # last chance, server must listen..
    sleep 10
    $network_script --host $HOST_IP $HOST_PORT --test-result $status --login $remote_user  SEND_RESULT $LOG_DIR/result.tar.xz
  fi
  rm -rf $LOG_DIR/result
  cd -
done

