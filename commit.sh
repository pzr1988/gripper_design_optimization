sudo rm -rdf data
git checkout master
git add --all
git commit -m "$1"
git push -u origin master
