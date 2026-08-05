PYTHON_OUTDIR = dist/python
NANOPB_OUTDIR = dist/nanopb

PROTO_SOURCES = $(shell find whad -name "*.proto")

all: python nanopb 

clean: clean_python clean_nanopb

clean_python:
	@echo "Remove python output directory ..."
	@rm $(PYTHON_OUTDIR) -rf

clean_nanopb:
	@echo "Remove nanopb output directory ..."
	@rm $(NANOPB_OUTDIR) -rf

python: clean_python
	@mkdir -p $(PYTHON_OUTDIR)
	protoc --experimental_allow_proto3_optional --python_out=$(PYTHON_OUTDIR) $(PROTO_SOURCES)

nanopb: clean_nanopb
	@mkdir -p $(NANOPB_OUTDIR)
	./nanopb/generator/protoc --experimental_allow_proto3_optional --nanopb_out=$(NANOPB_OUTDIR) $(PROTO_SOURCES)

