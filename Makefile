build_all: build_bdist build_sdist debuild

build_bdist:
	python3 setup.py bdist_wheel

build_sdist:
	python3 setup.py sdist

debuild:
	debuild

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf debuild/*

lint:
	pylint3 debian_crossgrader || true
