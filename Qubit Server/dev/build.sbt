organization := "org.labrad"

name := "QubitServer"

version := "0.2"

resolvers += "Maffoo bintray" at "http://dl.bintray.com/maffoo/maven"

crossPaths := false // don't add scala version suffix to jars

libraryDependencies ++= Seq(
  "org.labrad" % "jlabrad" % "0.2.0-M1" withSources()
)
