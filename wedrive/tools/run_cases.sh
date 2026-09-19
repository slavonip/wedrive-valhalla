#!/usr/bin/env bash
# Point 6: the real cross-border route, plus the controls that say the portal did not break or
# fake anything else.
set -u
R="docker exec vhdev /tmp/compose_route /regions/moldova/tiles /regions/romania/tiles"

case_() { # lat lon lat lon mode label
  printf '########## %s   [%s]\n' "$6" "$5"
  $R "$1" "$2" "$3" "$4" "$5"
  echo
}

echo "===== POINT 6: Chisinau -> Iasi. Chisinau is Moldova-only, Iasi is Romania-only."
case_ 47.0105 28.8638 47.1585 27.6014 both        "Chisinau -> Iasi"
case_ 47.0105 28.8638 47.1585 27.6014 both+portal "Chisinau -> Iasi"

echo "===== CONTROL A: a route wholly inside Moldova must be unchanged by the portal."
case_ 47.0105 28.8638 47.2075 27.8000 both        "Chisinau -> Ungheni"
case_ 47.0105 28.8638 47.2075 27.8000 both+portal "Chisinau -> Ungheni"

echo "===== CONTROL B: a route wholly inside Romania, likewise."
case_ 47.1585 27.6014 46.6750 28.0600 both        "Iasi -> Husi"
case_ 47.1585 27.6014 46.6750 28.0600 both+portal "Iasi -> Husi"
