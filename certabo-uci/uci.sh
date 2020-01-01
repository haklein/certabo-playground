#!/usr/bin/bash
pushd . > /dev/null
cd ~/src/certabo-playground/certabo-uci
ps auxw | grep certabo-uci.py | awk '{print $2} ' | while read pid; do kill $pid; done > /dev/null 2>&1 || true
python3 certabo-uci.py
popd > /dev/null
