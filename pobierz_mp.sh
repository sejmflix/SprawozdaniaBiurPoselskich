#!/bin/bash
curl -s 'https://api.sejm.gov.pl/sejm/term10/MP' \
| jq -r '
  (["id","firstName","secondName","lastName","firstLastName","club","districtNum","districtName","voivodeship","email","active"] | @csv),
  (.[] | [ .id, .firstName, .secondName, .lastName, .firstLastName, .club, .districtNum, .districtName, .voivodeship, .email, .active ] | @csv)
' > poslowie_term10.csv
