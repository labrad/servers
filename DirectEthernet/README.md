# Direct Ethernet Server

The direct ethernet server provides low-level access to ethernet ports, allowing
to send and receive raw ethernet packets when TCP, UDP or other higher-level
protocols are not available, e.g. for communicating with DAC and ADC boards.

This server is written in scala and built with [sbt](http://www.scala-sbt.org/).
You will need to have sbt installed to build from source. The following commands
are useful:

```
$ sbt compile      # compile the source
$ sbt test         # run automated tests
$ sbt run          # run the server, useful during development
$ sbt packArchive  # produce an installable package in target/DirectEthernet-<version>.tar.gz
```

To "install" the server, just unpack the archive file on the machine where it
is to be run. The archive includes a node .ini files, so if you unpack into a
directory that is searched by the node, it will find the server. Otherwise,
the bin directory in the archive contains start scripts for windows and *nix.

The server uses the [pcap4j](https://github.com/kaitoy/pcap4j) library to access
libpcap for packet capture. When the server starts you may see warnings in the
logs from `org.pcap4j.util.PropertiesLoader` indicating that it could not load
some values and is using a default value of null. The properties mechanism can
be used to override platform-dependent values for certain integer constants,
but in practice the defaults work fine on windows, mac and linux. These warnings
can be ignored unless you need to override the defaults on your platform. See
the pcap4j source for more details.
