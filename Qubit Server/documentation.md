# The Qubit Sequencer

(Also known as the "Qubit Server", or "that one that we have in Java".)

## Overview

The qubit sequencer lives in between the data taking code and the GHz FPGA server.
Its purpose is essentially organizational: it converts sequences defined in terms of qubit channels (e.g. XY, Z, readout) to sequences corresponding to hardware (e.g. DAC 14 A).

## Editing, Compiling, and Running

### Running

The qubit sequencer is written in Java, and as such uses the [JLabrad](https://github.com/martinisgroup/jlabrad) API.
The executable is a JAR file in this directory. It can be run on the command line with `java -jar QubitServer.jar`.
To run it with the LabRAD node/browser, make sure that the node can run Java files; see [the documentation in the node](https://github.com/martinisgroup/pylabrad/blob/master/labrad/node/__init__.py#L16) to make sure the node has your Java path configured correctly.

### Editing

The source code for the qubit sequencer is located under this directory, in dev/src/, organized according to Java standards.
The LabRAD settings (i.e. externally exposed functions) are defined in `QubitContext.java`.
To edit the code, it is highly recommended to use a full-featured Java IDE such as [IntelliJ](https://www.jetbrains.com/idea/) or [Eclipse](https://eclipse.org/).

### Compiling

Compiling the source into the runnable JAR file is most easily accomplished within your IDE.

#### IntelliJ IDEA

Included in this repo is `QubitServer.iml`, the IntelliJ project file, which should have these configurations already set up.
(Sharing it between users is untested as of now.)

1. Make sure your project is configured correctly
  1. File >> Project Structure >> Project >> Project language level: _at least 7_
  1. File >> Project Structure >> Modules
    1. Click the green +
      1. Navigate to your JLabrad checkout, and select the root JLabrad folder
      1. Import from Eclipse should work
    1. Select "QubitServer" again
    1. >> Dependencies
      1. Click the right-side green + >> Module Dependency... >> select JLabrad
      1. Again: + >> Library... >> Java >> navigate to JLabrad/lib and select `guava`
1. At this point, there should be no red squigglies indicating compile-time errors, and "Build >> Make Project" should compile successfully.
1. Now to export a JAR:
  1. File >> Project Structure >> Artifacts >> green + >> JAR >> From module with dependencies...
  1. Main Class >> click the `...` >> type `Qubit` and `QubitServer (org.labrad.qubits)` should show up >> OK
  1. OK
  1. Output directory: servers/Qubit Server
  1. Right click on `Qubit Server.jar`, select "Rename", and remove the space, to `QubitServer.jar`
  1. Check "Build on Make" to have IntelliJ handily re-compile (and overwrite) QubitServer.jar every time you make.

#### Eclipse

There is also `.project` in the repo, the Eclipse project file, which is hopefully correctly configured.
To create a JAR, I believe it's something like `File >> Export... >> JAR`, but I don't remember.

## Qubit Sequencer Structure

Java is a class-based, object-oriented language, and the qubit sequencer demonstrates this: there are well over 50 different classes and interfaces, each with its own file.
This makes it intimidating for the newcomer, but once you've figured out what the class is that you need to change, you can be confident that the code will work, or at least fail obviously.

The most important classes are listed here.

* `QubitContext`
  * Maintains the LabRAD context, and also includes all the publicly accessible settings of the qubit sequencer.
* `QubitServer`
  * Responsible for loading the configuration (wiring, hardware, etc.) when the server starts.
* `Experiment`
  * Represents the configuration of a single experiment: a list of `Device`
* `Device`
  * Ties together a list of `Channel` into a single conceptual device, such as a qubit. For example, a qubit typically has "FastBias", "IQ", and "Analog" channels.
* `Channel`
  * Represents a particular capability of the experiment.
  * The following types are currently available:
    * Analog: one half of an analog board (i.e. DAC A or B), used for Z-control
    * IQ: one microwave board, for XY control
    * FastBias: one of the four fiber connections on a DAC board to a FastBias card
    * ADC: either one ADC in average mode, or one channel of an ADC in demod mode
    * Trigger: for configuring the trigger pulses on a DAC board
    * Preamp: not used?
  * Most user interaction with the Qubit Sequencer is through channel objects.
* Note that `Experiment`, `Device`, and `Channel` objects are local to the context.
  * Created when the user calls `initialize`, with the [Builder pattern](en.wikipedia.org/wiki/Builder_pattern) (the builder classes are in the `templates` package).
* `ChannelData`
  * Holds the (pre- and post-deconvolved) data for SRAM based channels (e.g. IQ and Analog)
* `FpgaModel`
  * Represents an implementation of an FPGA board, such as an ADC board, or a DAC board configured into IQ or analog mode, for this experiment.
  * Holds references to its `Channel` objects, and calls them to get the actual SRAM data to send to the boards, as well as the `DacBoard` object, which represents the physical hardware.
  * Constructed as member variables of the `Experiment` class.
* `Resources`
  * List of physical resources available, e.g. DAC boards, FastBias cards, etc.
* `DacBoard`
  * Represents the physical FPGA boards.
  * Has info about build number, etc.
* `Resources` and `DacBoard` objects are constructed when the Qubit Sequencer starts (or later, if the wiring registry key is changed).

Now let's work through some "examples" to make this a bit more concrete:

* `SRAM IQ Data Fourier`: The user wants to define the SRAM data for a given XY channel.
  * There are three arguments to this function:
    * The channel ID, either specified as `("device name", "channel")` or `"device name"`
    * The data, an array of complex numbers
    * `t0`
  * The correct `IqChannel` is retrieved with `getChannel`
  * A new `IqDataFourier` object is created, and given to the channel.
  * When `buildSequence()` is called:
    * The data are deconvolved:
      * The `deconvolveSram` function is called for each `FpgaModelDac` instance
      * The `FpgaModelMicrowave` instance that holds our `IqChannel` retrieves the data with `getBlockData(blockName)`
      * It gets a `Future` for the deconvolved data from `IqDataFourier.deconvolve`
      * All of the futures are waited on back in `buildSequence()`
    * The actual SRAM waveform data is then taken from the `FpgaModelDac`, by way of `getSramDacBits`, which is implemented in `FpgaModelMicrowave`.
    * Back in `buildSequence()`, the raw SRAM data are added to a call to the `SRAM` function of the FPGA server.

Even though a lot of different classes were used to accomplish what may seem like a simple task, if you need to change anything there is one clearly defined place to do it.
If you want to change the way the deconvolution is done, look in the `IqDataFourier` class, while if you want to change the way the SRAM data are created, look in `getSramDacBits`.
