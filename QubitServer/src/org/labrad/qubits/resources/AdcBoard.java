package org.labrad.qubits.resources;

import org.labrad.qubits.enums.DacFiberId;
import org.labrad.qubits.enums.DcRackFiberId;

import com.google.common.base.Preconditions;

public class AdcBoard extends DacBoard implements Resource {

	
	
	public AdcBoard(String name) {
		super(name);
		// replace "dacBuild" with "adcBuild"
		this.buildType = "adcBuild";
	}
	
	@Override
	public void setFiber(DacFiberId fiber, BiasBoard board, DcRackFiberId channel) {
		Preconditions.checkArgument(false, "ADC board '%s' was given fibers!", getName());
	}

	public static Resource create(String name) {
		AdcBoard board = new AdcBoard(name);
		//System.out.println("makin AdcBoard wut wut: " + name);
		return board;
	}

}
