#!/usr/bin/bash
pushd .
cd ~/src/certabo-playground/certabo-uci
ps auxw | grep usbtool | awk '{print $2} ' | while read pid; do kill $pid; done > /dev/null 2>&1 || true
python3 certabo-uci.py --port /dev/ttyUSB0
popd
