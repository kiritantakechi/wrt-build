# An upgrade image must carry a signature of a trusted firmware key
# (r4s-release-pipeline D4): sysupgrade checks it with ucert against
# /etc/opkg/keys, where wrt-keyring puts the release keys, and refuses an image
# unsigned or changed since it was signed. wrt-update never forces it (-F).
# shellcheck shell=sh disable=SC2034 # read by fwtool_check_signature
REQUIRE_IMAGE_SIGNATURE=1
