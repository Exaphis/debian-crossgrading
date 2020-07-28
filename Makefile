deb_version = $(shell dpkg-parsechangelog -ldebian/changelog -S Version)
# version format: [epoch:]upstream_version[-debian_revision]
upstream_version = $(shell tmp='$(deb_version)'; tmp="$${tmp\#\#*:}"; echo $${tmp%%-*})

build_all: build_bdist build_sdist debuild

build_bdist:
	python3 setup.py bdist_wheel

build_sdist:
	python3 setup.py sdist

debuild: build_sdist
	mkdir debuild/debian-crossgrader-source
	tar -xf $(wildcard dist/*.tar.gz) -C debuild/debian-crossgrader-source --strip-components 1
	cp $(wildcard dist/*.tar.gz) debuild/debian-crossgrader_$(upstream_version).orig.tar.gz
	cp -r debian debuild/debian-crossgrader-source
	cd debuild/debian-crossgrader-source && debuild -us -uc

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf debuild/*

lint:
	pylint3 debian_crossgrader || true
