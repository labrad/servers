# Qubit Sequencer Server

The qubit sequencer server provides a higher-level interface for creating
sequences to be run on multiple qubits, managing the details of communicating
with the various DAC and ADC boards used by a particular set of qubits.

This server is written in scala and built with [sbt](http://www.scala-sbt.org/).
You will need to have sbt installed to build from source. The following commands
are useful:

```
$ sbt compile      # compile the source
$ sbt test         # run automated tests
$ sbt run          # run the server, useful during development
$ sbt packArchive  # produce an installable package in target/QubitServer-<version>.tar.gz
```

To "install" the server, just unpack the archive file on the machine where it
is to be run. The archive includes a node .ini files, so if you unpack into a
directory that is searched by the node, it will find the server. Otherwise,
the bin directory in the archive contains start scripts for windows and *nix.
