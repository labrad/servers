organization := "org.labrad"

name := "DirectEthernet"

version := "1.2.2"

scalaVersion := "2.11.7"
javacOptions ++= Seq("-source", "1.7", "-target", "1.7")

resolvers += "bintray" at "https://jcenter.bintray.com/"

libraryDependencies ++= Seq(
  "org.labrad" %% "scalabrad" % "0.4.1",
  "org.pcap4j" % "pcap4j-core" % "1.5.0"
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


