package org.labrad.qubits;

import org.labrad.data.Complex;
import org.labrad.data.Data;

public class ComplexArray {
	public final double[] re;
	public final double[] im;
	public final int length;
	public ComplexArray(double[] re, double[] im) {
		this.re = re;
		this.im = im;
		this.length = re.length;
	}
	
	public Data toData() {
		Data iq = Data.ofType("*c");
		iq.setArraySize(re.length);
		for (int i = 0; i < re.length; i++) {
			iq.setComplex(re[i], im[i], i);
		}
		return iq;
	}
	
	public static ComplexArray fromData(Data vals) {
		int len = vals.getArraySize();
		double[] re = new double[len];
		double[] im = new double[len];
		for (int i = 0; i < len; i++) {
			Complex c = vals.get(i).getComplex();
			re[i] = c.getReal();
			im[i] = c.getImag();
		}
		return new ComplexArray(re, im);
	}
}
