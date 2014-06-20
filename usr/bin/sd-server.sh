#!/bin/bash

WORK_DIR="/var/log/sd-test"
SD_GIT_DIR="$WORK_DIR/systemd"
SD_GIT_REPO="git://anongit.freedesktop.org/systemd/systemd"
RESULT_DIR="$WORK_DIR/results"
BACKUP_PWD=$PWD
PATCH_ENABLED=0
REPEATED_FOR_COMIPLATION=0

git_test_branch="pfmnc"
test_script="/usr/bin/sd-pfmnc-server.py"
test_commit=""
test_file="test.tar.xz"
recv_file="recv_result.tar.xz"
remote_user="pepek"
RECV_RESULT_DIR="/home/fedora" # .. it's better that machine can write to noncritical place

#IP="10.3.11.133"
IP="192.168.10.20"
PORT="4501"
HOST_IP="192.168.10.10"
HOST_PORT="4500"

################# FUNCTIONS #############################
basic_init() {
  if [[ ! -e $WORK_DIR ]]; then
    mkdir -p $WORK_DIR
    echo "0" > $WORK_DIR/patch_enabled
    PATCH_ENABLED=0
  fi

  if [[ -e $WORK_DIR/patch_enabled ]]; then
    PATCH_ENABLED=$(cat $WORK_DIR/patch_enabled)
    if [[ $PATCH_ENABLED != 0 && $PATCH_ENABLED != 1 ]]; then
      echo "0" > $WORK_DIR/patch_enabled
      PATCH_ENABLED=0
    fi
  fi

  if [[ ! -e $RESULT_DIR  ]]; then
    mkdir -p $RESULT_DIR
  fi
  
  if [[ ! -e $SD_GIT_DIR ]]; then
    mkdir -p $SD_GIT_DIR
    cd $SD_GIT_DIR/..
    git clone $SD_GIT_REPO
    cd $SD_GIT_DIR
    git config user.name "test server"
    git config user.mail "test@test.com"
    git branch $git_test_branch
  else # download new commits in master branch
    cd $SD_GIT_DIR
    # check if last tested commit has own directory (== test finished)
    # if has not then reset test branch (pfmnc probably) to this commit
    last_commit_dir=$(git cherry $git_test_branch master | grep -B 1 -m 1 "^+" | head -n 1 | sed -E "s/^..(......).*/\1_0/")
    if [[ -e $RESULT_DIR/$last_commit_dir ]]; then
      git checkout $git_test_branch
      git reset --hard HEAD^
      PATCH_ENABLED=0
    fi
    git checkout master
    git pull
    
    cd -
  fi
  cd $BACKUP_PWD
}

#mini TODO: check git operations
# 0 - test prepared
is_test_prepared() {
  if [[ $PATCH_ENABLED -eq 0 ]]; then # send complete source code
    # always set test branch for testing machine!!
    cd $SD_GIT_DIR 
    git checkout $git_test_branch

    cd $WORK_DIR
    tar --posix -Jcf $WORK_DIR/$test_file ${SD_GIT_DIR#$WORK_DIR/}

    cd $SD_GIT_DIR
    test_commit=$(git show | head -n 1 | cut -d " " -f 2)
    git checkout master

    cd $BACKUP_PWD
    return 0
  fi

  cd $SD_GIT_DIR
  git pull # update local master branch
  git checkout $git_test_branch
  test_commit=$(git cherry $git_test_branch master | grep -m 1 "^\+")
  test_commit=${test_commit#"+ "} # remove prefix
  if [[ $test_commit == "" ]]; then
    git checkout master
    cd -
    return 1
  fi

  git cherry-pick $test_commit
  git diff HEAD^ > $WORK_DIR/sd_test.patch
  git checkout master

  cd $WORK_DIR
  tar --posix -Jcf $test_file sd_test.patch
  rm -f $WORK_DIR/sd_test.patch
  
  cd $BACKUP_PWD
  return 0
}

send_test_rq() {
  if [[ $PATCH_ENABLED -eq 0 ]]; then
    patch_param=""
  else
    patch_param="--patch"
  fi

  
  $test_script --host $HOST_IP $HOST_PORT $patch_param --login $remote_user  RQ_TEST $WORK_DIR/$test_file
  status=$?

  if [[ $status -eq 5 ]]; then
    PATCH_ENABLED=0
    echo "0" > $WORK_DIR/patch_enabled
    is_test_prepared
    $test_script --host $HOST_IP $HOST_PORT --login $remote_user RQ_TEST $WORK_DIR/$test_file
    status=$?
  else
    PATCH_ENABLED=1
    echo "1" > $WORK_DIR/patch_enabled
  fi

  return $status
}

recv_result() {
 $test_script --bind $IP $PORT RECV_RESULT $recv_file
 return $?
}

##################### MAIN #############################

basic_init

while [[ 1 ]]; do # run forever and ever - if you crashed down, I killed you...I hope...
  is_test_prepared
  if [[ $? -eq 0 ]];then
    #TODO: check better and give echo on BIG problem
    echo "Sendings"
    sleep_time=0
    send_test_rq
    while [[ $? -ne 0 ]]; do
      sleep $sleep_time
      [[ $sleep_time -lt 600 ]] && sleep_time=$[ $sleep_time + 60 ]
      send_test_rq
    done
    echo "Sended: $status"

    recv_result
    status=$?
    while [[ $status -gt 0 && $status -lt 8 ]]; do
      recv_result
      status=$?
      sleep 1
    done
    echo "Recieved: $status"

    if [[ $status -eq 9 && $REPEATED_FOR_COMPILATION -eq 0 ]]; then
      # failed on compilation - maybe error on make clean etc.
      # send complete source code
      PATCH_ENABLED=0
      REPEATED_FOR_COMPILATION=1
      rm -f $RECV_RESULT_DIR/$recv_file
      continue # if it is not permanent error, do not store results
    fi

    REPEATED_FOR_COMPILATION=0

    tar -Jxf $RECV_RESULT_DIR/$recv_file -C $RECV_RESULT_DIR
    origin_label=$( tar -tf $RECV_RESULT_DIR/$recv_file | head -n 1 )
    if [[ $origin_label == ""  ]]; then continue; fi # hypotetic situation
    #  mkdir -p $RESULT_DIR/$origin_label # only if new hiearchy
    test_commit_edited=$(echo $test_commit | sed -r "s/^(......).*$/\1/")
    mv $RECV_RESULT_DIR/$origin_label  $RESULT_DIR/${test_commit_edited}_0 # think up hiearchy again...
    rm -f $RECV_RESULT_DIR/$recv_file

    systemd-pfmnc-graph.py -i $RESULT_DIR -o $RESULT_DIR -l 30 --auto-width -t total -c "A X"
    
  else
    echo "Nothing for testing."
    sleep 600 # good interval for me
  fi
done

