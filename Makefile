# This Makefile wraps commands used to set up the learning module and 
# start the Tellina server.

LR_MODULE=tellina_learning_module

git: 
	# Update learning submodule
	git submodule update --remote

	# Setup database tables
	python3 manage.py makemigrations
	python3 manage.py migrate

run: 
	# Set PYTHONPATH 
	export PYTHONPATH=`pwd`
	# Set up data files used in the learning module
	tar xf $(LR_MODULE)/data/bash/vocab.tar.xz --directory $(LR_MODULE)/data/bash/
	tar xf $(LR_MODULE)/data/bash.final/vocab.tar.xz --directory $(LR_MODULE)/data/bash.final/
	# Set up nlp tools
	tar xf $(LR_MODULE)/nlp_tools/spellcheck/most_common.tar.xz --directory $(LR_MODULE)/nlp_tools/spellcheck/
	# Run server
	python3 manage.py runserver 0.0.0.0:8000    

clean: 
	# Destroy database and migrations	 
	rm -rf db.sqlite3 tellina/migrations 
