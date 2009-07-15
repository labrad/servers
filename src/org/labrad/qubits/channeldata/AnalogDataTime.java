package org.labrad.qubits.channeldata;

import java.util.List;

import org.labrad.data.Data;
import org.labrad.data.Request;
import org.labrad.qubits.channels.AnalogChannel;
import org.labrad.qubits.util.PacketResultHandler;

import com.google.common.base.Preconditions;

public class AnalogDataTime extends AnalogDataBase {

	private double[] rawData = null;
	private int[] deconvolvedData = null;
	
	public AnalogDataTime(double[] data, boolean isDeconvolved) {
		this.rawData = data;
		if (isDeconvolved) {		
			int[] values = new int[data.length];
			for (int i = 0; i < data.length; i++) {
				values[i] = (int)(data[i] * 0x1fff) & 0x3fff;
			}
			this.deconvolvedData = values;
		}
		setDeconvolved(isDeconvolved);
	}

	public void checkLength(int expected) {
		LengthChecker.checkLengths(rawData.length, expected);
	}
	
	@Override
	public PacketResultHandler requestDeconvolution(Request req) {
		Data iq = Data.ofType("*v");
		iq.setArraySize(rawData.length);
		for (int i = 0; i < rawData.length; i++) {
			iq.setValue(rawData[i], i);
		}
		AnalogChannel channel = getChannel();
		String board = channel.getDacBoard().getName();
		double[] rates = channel.getSettlingRates();
		double[] times = channel.getSettlingTimes();
		req.add("Board", Data.valueOf(board));
		req.add("DAC", Data.valueOf(channel.getDacId().toString()));
		req.add("Set Settling", Data.clusterOf(Data.valueOf(rates), Data.valueOf(times)));
		final int idx = req.addRecord("Correct", iq);
		return new PacketResultHandler() {
			public void handleResult(List<Data> data) {
				deconvolvedData = data.get(idx).getIntArray();
				setDeconvolved(true);
			}
		};
	}
	
	@Override
	public int[] getDeconvolved() {
		Preconditions.checkState(isDeconvolved(), "Data has not yet been deconvolved");
		return deconvolvedData;
	}
}
