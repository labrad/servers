organization := "org.labrad"

name := "QubitServer"

version := "0.7.1"

scalaVersion := "2.11.7"

resolvers += "bintray" at "http://jcenter.bintray.com/"

libraryDependencies ++= Seq(
  "com.google.guava" % "guava" % "18.0",
  "org.labrad" %% "scalabrad" % "0.5.2",
  "org.scalatest" %% "scalatest" % "2.2.4" % "test"
)

// use sbt-pack to create packaged, runnable version of qubit server
packSettings
packMain := Map("qubitserver" -> "org.labrad.qubits.QubitServer")
packResourceDir := Map(
  // copy contents of src/main/pack to the root of the packed archive
  (sourceDirectory in Compile).value / "pack" -> ""
)
