@echo off
git fetch origin
git reset --hard origin/main
git pull
git log -1