!#/bin/bash

find . -path ./.git -prune -o -type f -name "*.py" -not -name "output.txt" -exec sh -c 'echo "{}"; cat "{}"' \; > output.txt