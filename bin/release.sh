#!/bin/bash -e

function require_clean_work_tree () {
    # Update the index
    git update-index -q --ignore-submodules --refresh
    err=0

    # Disallow unstaged changes in the working tree
    if ! git diff-files --quiet --ignore-submodules --
    then
        echo >&2 "cannot $1: you have unstaged changes."
        git diff-files --name-status -r --ignore-submodules -- >&2
        err=1
    fi

    # Disallow uncommitted changes in the index
    if ! git diff-index --cached --quiet HEAD --ignore-submodules --
    then
        echo >&2 "cannot $1: your index contains uncommitted changes."
        git diff-index --cached --name-status -r --ignore-submodules HEAD -- >&2
        err=1
    fi

    if [ $err = 1 ]
    then
        echo >&2 "Please commit or stash them."
        exit 1
    fi
}

echo "This script increments build version and merges current master into production"
echo "  with an appropriate tag."
echo ""
echo "Pass a name of version number to be incremented ('major', 'minor' or 'patch')"

PROJECT_DIR="$(dirname "${BASH_SOURCE[0]}")/.."
BUMPED_VERSION="$1"

if [ -z "${BUMPED_VERSION}" ]; then
    echo >&2 "You must specify what version number to increment"
    exit 1
fi

CURRENT_BRANCH=$(git symbolic-ref -q HEAD)
CURRENT_BRANCH=${CURRENT_BRANCH##refs/heads/}

if [ "${CURRENT_BRANCH}" != "master" ]; then
    echo >&2 "You must be on 'master' branch."
    exit 1
fi

require_clean_work_tree 

git checkout production
git merge -X theirs --squash master

# Execute tests (just in case)
python "${PROJECT_DIR}/setup.py" test
bumpversion --allow-dirty --message 'New release on {utcnow}: {new_version}' "${BUMPED_VERSION}"

git push origin production --tags

git checkout master
git merge -X theirs production -m "Updating version number(s)" # Update version string(s)
git push