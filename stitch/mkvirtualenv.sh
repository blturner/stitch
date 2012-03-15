#!/bin/bash
#
# Usage:
# $ mkvirtualenv.sh [--rebuild] virtualenv_name project_dir git_branch_name

# TODO: Currently assumes WORKON_HOME is set.
# TODO: Implement [--rebuild] option

export PIP_VIRTUALENV_BASE=$WORKON_HOME
export PIP_RESPECT_VIRTUALENV=true

PROJECT_DIR=$2
GIT_BRANCH_NAME=$3
VM_DIR="$WORKON_HOME/$1" # Location of the virtualenv

# Create the virtualenv if it doesn't exist
if [ -d "$VM_DIR" ]
  then
    echo "$VM_DIR already exists."
  else
    virtualenv $VM_DIR
fi

PIP_REQUIREMENTS=`find $PROJECT_DIR -name requirements.txt`
`cd $PROJECT_DIR && git checkout $GIT_BRANCH_NAME`
`source $VM_DIR/bin/activate && pip install -r $PIP_REQUIREMENTS`
