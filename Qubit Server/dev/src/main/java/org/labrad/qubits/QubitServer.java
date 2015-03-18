package org.labrad.qubits;

import java.util.Iterator;
import java.util.List;
import java.util.concurrent.ExecutionException;

import org.labrad.AbstractServer;
import org.labrad.Connection;
import org.labrad.RequestCallback;
import org.labrad.Servers;
import org.labrad.annotations.ServerInfo;
import org.labrad.data.Context;
import org.labrad.data.Data;
import org.labrad.data.Request;
import org.labrad.events.MessageEvent;
import org.labrad.events.MessageListener;
import org.labrad.qubits.resources.AdcBoard;
import org.labrad.qubits.resources.DacBoard;
import org.labrad.qubits.resources.Resources;

@ServerInfo(name = "Qubit Sequencer",
    doc = "Builds and Runs qubit sequences"
        + "\n\n"
        + "This server is designed to help you build sequences to control the "
        + "numerous devices involved in a multi-qubit experiment.  In general, "
        + "this is complicated by the fact that the way the control sequence "
        + "is constructed depends on the wiring among all the various devices, "
        + "and by the fact that the sequence itself must be properly constructed "
        + "to ensure that all the boards run, stay in sync, and return timing "
        + "results as appropriate."
        + "\n\n"
        + "Information about the wiring setup (which should not change very often) "
        + "is loaded from the registry at ['', 'Servers', 'Qubit Server', 'Wiring'].  "
        + "Please do not modify this directly, but rather use the 'WiringEditor.py' "
        + "script to make changes.  The wiring information is reloaded whenever this "
        + "registry entry is changed."
        + "\n\n"
        + "To build sequences, the setup is described as a list of devices, each "
        + "of which can have any number of channels.  These channels are one of a "
        + "small set of types, such as 'Iq' for microwaves or 'FastBias' for flux "
        + "or SQUID bias.  Many of the commands used to build up the sequence require "
        + "you to specify which channel or channels the command should affect.  "
        + "Channels are identified either by a pair of strings "
        + "(<device name>, <channel name>), or a single string <device name> "
        + "if the device has only one channel of the type needed for the command."
        + "\n\nVersion 0.4.10.")
public class QubitServer extends AbstractServer {

  private Context wiringContext;

  @Override
  public void init() {
    Connection cxn = getConnection();
    wiringContext = cxn.newContext();
    try {
      loadWiringConfiguration();
    } catch (Exception e) {
      throw new RuntimeException(e);
    }
    // automatically reload the wiring configuration when it changes
    cxn.addMessageListener(new MessageListener() {
      @Override
      public void messageReceived(MessageEvent e)  {
        if (e.getMessageID() == 55443322L) {
          String serverName = e.getData().getClusterAsList().get(1).getString();
          if (serverName.equals(Constants.GHZ_DAC_SERVER)) {
            System.out.println("Server connected: " + Constants.GHZ_DAC_SERVER + " -- refreshing wiring.");
            try {
              Thread.sleep(1000);
            } catch (InterruptedException e1) {
              e1.printStackTrace();
            }
            loadWiringConfiguration();
          }
        }
        else if (e.getContext().equals(wiringContext)) {
          wiringContext = getConnection().newContext();
          loadWiringConfiguration();
        }
      }
    });
    Request req = startRegistryRequest();
    req.add("Notify on Change", Data.valueOf(wiringContext.getLow()),
        Data.valueOf(true));
    Request req2 = Request.to("Manager", wiringContext);
    req2.add("Subscribe to Named Message", Data.valueOf("Server Connect"), Data.valueOf(55443322L),
        Data.valueOf(true));
    try {
      cxn.sendAndWait(req);
      cxn.sendAndWait(req2);
    } catch (Exception e) {
      throw new RuntimeException(e);
    }
  }

  @Override
  public void shutdown() {
    System.out.println("Qubit sequencer shutting down.");
  }

  /**
   * Create a request for the registry
   */
  private Request startRegistryRequest() {
    return Request.to(Constants.REGISTRY_SERVER, wiringContext);
  }

  /**
   * Load the current wiring configuration from the registry.
   */
  public void loadWiringConfiguration() {
    System.out.println("Updating wiring configuration...");

    // load wiring configuration from the registry
    Request req = startRegistryRequest();
    req.add("cd", Data.valueOf(Constants.WIRING_PATH),
        Data.valueOf(true)); // create the directory if needed
    int idx = req.addRecord("get", Data.valueOf(Constants.WIRING_KEY)); //,
    // Data.valueOf(Constants.WIRING_TYPE)); // no longer enforcing wiring type ==> cluster fuck!
    List<Data> ans;
    try {
      ans = getConnection().sendAndWait(req);
    } catch (InterruptedException ex) {
      throw new RuntimeException(ex);
    } catch (ExecutionException ex) {
      throw new RuntimeException(ex);
    }

    // create objects for all resources
    List<Data> resources = ans.get(idx).get(0).getClusterAsList();
    //List<Data> resources = ans.get(idx).get(0).getDataList();
    List<Data> fibers = ans.get(idx).get(1).getDataList();
    List<Data> microwaves = ans.get(idx).get(2).getDataList();
    Resources.updateWiring(resources, fibers, microwaves);

    System.out.println("Wiring configuration updated.");

    this.loadBuildProperties();
  }

  /**
   * we make a BuildLoader for every DAC/ADC board. we run them asynchronously to get build information
   * from both the FPGA server and the registry.
   * @author pomalley
   *
   */
  private class BuildLoader implements RequestCallback {

    private DacBoard myBoard;
    private boolean gotBuildNumber;

    public BuildLoader(DacBoard b) {
      myBoard = b;
      gotBuildNumber = false;
    }

    public void run() {
      // build and send request to the FPGA server
      Request req = Request.to(Constants.GHZ_DAC_SERVER, wiringContext);
      req.add("Select Device", Data.valueOf(myBoard.getName()));
      req.add("Build Number");

      // TODO: let's temporarily try doing this synchronously
      // to see if we can figure out why neither onSuccess or onFailure
      // is being called when the FPGA server is restarted.
      //getConnection().send(req, this);
      List<Data> resp;
      try {
        resp = getConnection().sendAndWait(req);
        onSuccess(req, resp);
      } catch (InterruptedException | ExecutionException e) {
        onFailure(req, e);
      }

      //System.out.println("Sent request for board " + myBoard.getName());
      //System.out.println(req.getServerName() + " (" + req.getServerID() + ")");

    }

    @Override
    public void onSuccess(Request request, List<Data> response) {
      if (!gotBuildNumber) {
        // we got the build number from the FPGA server
        String buildNumber = response.get(1).getString();
        myBoard.setBuildNumber(buildNumber);
        System.out.println("Board " + myBoard.getName() + " has build number " + myBoard.getBuildNumber());
        gotBuildNumber = true;
        // send out a new packet to the registry to look up info on this build number
        sendRegistryRequest();
      } else {
        // we have the build details from the registry
        myBoard.loadProperties(response.get(1));
        System.out.println("Loaded build properties for board " + myBoard.getName());
      }
    }

    @Override
    public void onFailure(Request request, Throwable cause) {
      if (!gotBuildNumber) {
        // we failed to get the build number from the FPGA server
        System.out.println("Board " + myBoard.getName() + " failed to get build number: " + //cause.getMessage() +
            " Using default build number (5 for DAC, 1 for ADC).");
        myBoard.setBuildNumber("-1");
        gotBuildNumber = true;
        // send out a packet to the registry anyway to get the details
        sendRegistryRequest();
      } else {
        // we failed to get the build details from the registry
        System.out.println("Exception when looking up ADC/DAC build properties: " + cause.getMessage() + ". Using default values.");
        if (myBoard instanceof AdcBoard)
          myBoard.loadProperties(Constants.DEFAULT_ADC_PROPERTIES_DATA);
        else
          myBoard.loadProperties(Constants.DEFAULT_DAC_PROPERTIES_DATA);
      }
    }

    private void sendRegistryRequest() {
      Request regReq = startRegistryRequest();
      regReq.add("cd", Data.valueOf(Constants.BUILD_INFO_PATH));
      String number = myBoard.getBuildNumber();
      if (number.equals("-1") && myBoard instanceof AdcBoard)
        number = "1";
      else if (number.equals("-1"))
        number = "5";
      regReq.add("get", Data.valueOf(myBoard.getBuildType() + number));

      // TODO: synchronous as above
      //getConnection().send(regReq, this);
      List<Data> resp;
      try {
        resp = getConnection().sendAndWait(regReq);
        onSuccess(regReq, resp);
      } catch (InterruptedException | ExecutionException e) {
        onFailure(regReq, e);
      }
    }
  }

  /**
   * Load the build properties for the ADC and DAC boards.
   * @throws ExecutionException 
   * @throws InterruptedException 
   */
  public void loadBuildProperties() {
    System.out.println("Load DAC/ADC build properties...");
    Resources current = Resources.getCurrent();
    List<DacBoard> dacs = current.getAll(DacBoard.class);
    System.out.println("dacs.size() = " + dacs.size());
    // make and start a request to do look up build numbers and properties for each board
    for (DacBoard board : dacs) {
      BuildLoader bl = new BuildLoader(board);
      bl.run();
    }

    // check to see that we've set build properties
    while (dacs.size() > 0) {
      for (Iterator<DacBoard> it = dacs.iterator(); it.hasNext();) {
        if (it.next().havePropertiesLoaded())
          it.remove();
      }
      int n = 0;
      if (dacs.size() > 0) {
        System.out.println("Waiting on " + dacs.size() + " boards...");
        try {
          Thread.sleep(1000);
          n++;
          if (n > 30) {
            System.err.println("Timeout when waiting for board build number info!");
            dacs.clear();
          }
        } catch (InterruptedException e) {
          System.err.println("Error while waiting for DAC board info!");
          e.printStackTrace();
        }
      } else {
        System.out.println("All boards loaded.");
      }
    }
    System.out.println("DAC/ADC build properties loaded.");
  }

  /**
   * Run this server.
   */
  public static void main(String[] args) {
    Servers.runServer(QubitServer.class, QubitContext.class, args);
  }
}
