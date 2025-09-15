#!/bin/bash
CHROME_VERSION="121.0.6167.184"
wget -q https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_${CHROME_VERSION}-1_amd64.deb
sudo apt-get install -y ./google-chrome-stable_${CHROME_VERSION}-1_amd64.deb
rm google-chrome-stable_${CHROME_VERSION}-1_amd64.deb
