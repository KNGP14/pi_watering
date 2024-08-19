#!/bin/bash

args=""
i=1;
for arg in "$@" 
do
    args="$args $arg";
    i=$((i + 1));
done

DIR=`dirname "$0"`
python3="$DIR/venv/bin/python3"
if [ ! -f "$python3" ]; then
    python3="$DIR/venv/Scripts/python.exe"
fi

$python3 pi_watering.py $args