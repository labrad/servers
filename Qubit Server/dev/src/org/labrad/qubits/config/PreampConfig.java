package org.labrad.qubits.config;

import java.util.Arrays;
import java.util.Map;

import org.labrad.data.Data;
import org.labrad.qubits.channels.PreampChannel;

import com.google.common.base.Preconditions;
import com.google.common.collect.Maps;

public class PreampConfig {
  private static final String[] highPassFilterNames = new String[] {
    "DC", "3300", "1000", "330", "100", "33", "10", "3.3"
  };
  private static final long[] highPassFilterVals = new long[] {
    0, 1, 2, 3, 4, 5, 6, 7
  };
  private static final Map<String, Long> highPassFilterMap = Maps.newHashMap();
  private static final String highPassAllowedNames;

  private static final String[] lowPassFilterNames = new String[] {
    "0", "0.22", "0.5", "1", "2.2", "5", "10", "22"
  };
  private static final long[] lowPassFilterVals = new long[] {
    0, 1, 2, 3, 4, 5, 6, 7
  };
  private static final Map<String, Long> lowPassFilterMap = Maps.newHashMap();
  private static final String lowPassAllowedNames;

  static {
    for (int i = 0; i < highPassFilterNames.length; i++) {
      highPassFilterMap.put(highPassFilterNames[i], highPassFilterVals[i]);
    }
    highPassAllowedNames = Arrays.toString(highPassFilterNames);
    for (int i = 0; i < lowPassFilterNames.length; i++) {
      lowPassFilterMap.put(lowPassFilterNames[i], lowPassFilterVals[i]);
    }
    lowPassAllowedNames = Arrays.toString(lowPassFilterNames);
  }


  long highPass, lowPass;
  boolean polarity;
  long offset;

  public PreampConfig(long offset, boolean polarity, String highPass, String lowPass) {
    Preconditions.checkArgument(highPassFilterMap.containsKey(highPass),
        "Invalid high-pass filter value '%s'.  Must be one of %s", highPass, highPassAllowedNames);
    Preconditions.checkArgument(lowPassFilterMap.containsKey(lowPass),
        "Invalid low-pass filter value '%s'.  Must be one of %s", lowPass, lowPassAllowedNames);
    this.offset = offset;
    this.polarity = polarity;
    this.highPass = highPassFilterMap.get(highPass);
    this.lowPass = lowPassFilterMap.get(lowPass);

  }

  public SetupPacket getSetupPacket(PreampChannel ch) {
    String chName = ch.getPreampBoard().getName();
    int linkNameEnd = chName.indexOf("Preamp") - 1;
    String linkName = chName.substring(0, linkNameEnd);
    long cardId = Long.valueOf(chName.substring(linkNameEnd + "Preamp".length() + 2));

    Data data = Data.ofType("(ss)(sw)(s(s(wwww)))(s)");
    data.get(0).setString("Connect", 0).setString(linkName, 1);
    data.get(1).setString("Select Card", 0).setWord(cardId, 1);
    data.get(2).setString("Register", 0).setString(ch.getPreampChannel().toString().toUpperCase(), 1, 0)
    .setWord(highPass, 1, 1, 0)
    .setWord(lowPass, 1, 1, 1)
    .setWord(polarity ? 1L : 0L, 1, 1, 2)
    .setWord(offset, 1, 1, 3);
    data.get(3).setString("Disconnect", 0);

    String state = String.format("%s%s: offset=%d polarity=%b highPass=%d lowPass=%d",
        ch.getPreampBoard().getName(), ch.getPreampChannel(), offset, polarity, highPass, lowPass);

    return new SetupPacket(state, data);
  }
}
