organization := "org.labrad"

name := "DirectEthernet"

version := "1.0.0-M1"

scalaVersion := "2.11.6"

resolvers += "bintray" at "https://jcenter.bintray.com/"
resolvers += "maffoo" at "https://dl.bintray.com/maffoo/maven"

libraryDependencies ++= Seq(
  "org.labrad" %% "scalabrad" % "0.2.0-M6",
  "org.pcap4j" % "pcap4j-core" % "1.4.0"
)

// testing
libraryDependencies ++= Seq(
  "org.scalatest" %% "scalatest" % "2.2.0" % "test"
)
fork in Test := true

// use sbt-pack to create packaged, runnable artifacts
packSettings
packMain := Map("directethernet" -> "org.labrad.ethernet.server.DirectEthernet")
packResourceDir := Map(
  // copy contents of src/main/pack to the root of the packed archive
  (sourceDirectory in Compile).value / "pack" -> ""
)


