build:
	python3 setup.py sdist bdist_wheel

clean:
	rm -r build/
	rm -r dist/
	rm -r *.egg-info

lint:
	pylint3 debian_crossgrader || true
