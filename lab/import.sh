#!/usr/bin/env bash
# Imports libgit2 into the local p4d: base snapshot, then each first-parent upstream commit as a submitted CL.
set -euo pipefail
LAB=${LAB:?set LAB to the lab directory}
source "$LAB/env.sh"
BASE=36b887915
UP=$LAB/upstream
WS=$LAB/ws
mkdir -p $WS
p4 client -o lab-ws | sed "s#^Root:.*#Root:\t$WS#" | sed '/^View:/,$d' > /tmp/lab-client.spec
printf 'View:\n\t//depot/libgit2/... //lab-ws/...\n' >> /tmp/lab-client.spec
p4 client -i < /tmp/lab-client.spec
keep() { grep -v '^tests/resources/' ; }

# base snapshot
(cd $UP && git archive $BASE) | tar -x -C $WS --exclude='tests/resources'
cd $WS
find . -type f | sed 's#^\./##' | p4 -x - add >/dev/null
p4 submit -d "libgit2 import at upstream $BASE" | tail -1

echo -e "cl\tsha\tsubject" > $LAB/cls.tsv
for C in $(cd $UP && git rev-list --first-parent --reverse $BASE..main | head -25); do
  cd $UP
  subject=$(git log -1 --format=%s $C)
  changes=$(git diff --no-renames --name-status $C^1 $C | awk '{print $1"\t"$2}' | grep -v $'\ttests/resources/' || true)
  [ -z "$changes" ] && continue
  cd $WS
  while IFS=$'\t' read -r st path; do
    case $st in
      M) p4 edit "$path" >/dev/null; (cd $UP && git show "$C:$path") > "$path" ;;
      A) mkdir -p "$(dirname "$path")"; (cd $UP && git show "$C:$path") > "$path"; p4 add "$path" >/dev/null ;;
      D) p4 delete "$path" >/dev/null ;;
    esac
  done <<< "$changes"
  cl=$(p4 submit -d "$subject (upstream ${C:0:9})" | grep -oE 'Change [0-9]+ submitted' | grep -oE '[0-9]+')
  echo -e "$cl\t${C:0:9}\t$subject" >> $LAB/cls.tsv
done
p4 changes -m 3 //depot/...
