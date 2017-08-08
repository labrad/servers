-- Protocol definitions and packet dissectors for GHz FPGAs
--
-- To use this in wireshark, you can copy this file into your local wireshark
-- plugin directory. You can find the plugin directory for your platform by
-- looking at the wireshark help menu. This is typically something like:
--
--  windows: C:/Users/<user>/AppData/Roaming/Wireshark/plugins/
--  linux: ~/.wireshark/plugins/
--
-- Note that this uses heuristic dissectors to identify the fpga packets.
-- Heuristic dissectors were first exposed to the lua API in version 1.11.3.
-- On some linux distributions, the packaged version of wireshark is too old,
-- so you may have to build from source.
--
-- The basic structure here is as follows:
--
-- * We define a set of protocols, one general protocol each for DAC and ADC
--   as well as one protocol for each specific message type (register write,
--   SRAM write, etc.). We also define fields for each protocol which represent
--   important chunks of data within the packet, such as an ethernet address
--   or a number like the readback mode. We follow the convention of the lua
--   examples from the wireshark docs and use the prefix `p_` for protocol
--   variables and the prefix `f_` for field variables.
--
-- * We then define dissector functions for the protocols. These are called by
--   by wireshark with information about a captured packet and the dissector
--   function is responsible for extracting information from the packet and
--   associating it with the fields we defined previously.
--
-- For more details of the wireshark lua API, see:
-- https://www.wireshark.org/docs/wsdg_html_chunked/wsluarm_modules.html


-- DAC protocols and packet fields
--
local p_dac = Proto("ghz_dac", "GHz DAC")
local f_dac_dest = ProtoField.ether("ghz_dac.dest", "Destination")
local f_dac_source = ProtoField.ether("ghz_dac.source", "Source")
local f_dac_type = ProtoField.uint16("ghz_dac.msg_type", "Message Type",
  base.DEC,
  {
    [56] = "Register Write",
    [70] = "Register Read",
    [1026] = "SRAM Write",
    [528] = "JumpTable Write"
  }
)
p_dac.fields = { f_dac_dest, f_dac_source, f_dac_type }


local p_dac_reg_write = Proto("ghz_dac.reg_write","GHz DAC Register Write")
local f_dac_start = ProtoField.uint8("ghz_dac.reg_write.start", "Start",
  base.DEC,
  {
    [0] = "no start",
    [1] = "master",
    [2] = "test",
    [3] = "slave",
  }
)
local f_dac_readback = ProtoField.uint8("ghz_dac.reg_write.readback", "Readback",
  base.DEC,
  {
    [0] = "no readback",
    [1] = "readback after 2 us",
    [2] = "readback after I2C"
  }
)
p_dac_reg_write.fields = { f_dac_start, f_dac_readback }


local p_dac_reg_read = Proto("ghz_dac.reg_read", "GHz DAC Register Read")


local p_dac_sram_write = Proto("ghz_dac.sram_write", "GHz DAC SRAM Write")


local p_dac_jumptable_write = Proto("ghz_dac.jumptable_write", "GHz DAC JumpTable Write")


-- Table of DAC protocols indexed by data length (excluding ethernet header)
local dac_protos = {
  [56] = p_dac_reg_write,
  [70] = p_dac_reg_read,
  [1026] = p_dac_sram_write,
  [528] = p_dac_jumptable_write
}


-- ADC Protocols and packet fields
--
local p_adc = Proto("ghz_adc", "GHz ADC")
local f_adc_dest = ProtoField.ether("ghz_adc.dest", "Destination")
local f_adc_source = ProtoField.ether("ghz_adc.source", "Source")
local f_adc_type = ProtoField.uint16("ghz_adc.msg_type", "Message Type",
  base.DEC,
  {
    [59] = "Register Write",
    [46] = "Register Read",
    [1026] = "SRAM Write",
    [48] = "Demodulator Output",
    [1024] = "Average Output",
  }
)
p_adc.fields = { f_adc_dest, f_adc_source, f_adc_type }


local p_adc_reg_write = Proto("ghz_adc.reg_write", "GHz ADC Register Write")


local p_adc_reg_read = Proto("ghz_adc.reg_read", "GHz ADC Register Read")


local p_adc_sram_write = Proto("ghz_adc.sram_write", "GHz ADC SRAM Write")


local p_adc_demod_output = Proto("ghz_adc.demod_output", "GHz ADC Demod Output")


local p_adc_average_output = Proto("ghz_adc.average_output", "GHz ADC Average Output")


-- Table of ADC protocols indexed by data length (excluding ethernet headers)
local adc_protos = {
  [59] = p_adc_reg_write,
  [46] = p_adc_reg_read,
  [1026] = p_adc_sram_write,
  [48] = p_adc_demod_output,
  [1024] = p_adc_average_output
}


-- Helper function to decide if a MAC address belongs to a DAC board
function is_dac_mac(range)
  local bytes = range:bytes()
  local prefix = { 0x00, 0x01, 0xCA, 0xAA, 0x00 }
  for i=1,5 do
    if bytes:get_index(i-1) ~= prefix[i] then
      return false
    end
  end
  return true
end


-- Helper function to decide if a MAC address belongs to an ADC board
function is_adc_mac(range)
  local bytes = range:bytes()
  local prefix = { 0x00, 0x01, 0xCA, 0xAA, 0x01 };
  for i=1,5 do
    if bytes:get_index(i-1) ~= prefix[i] then
      return false
    end
  end
  return true
end


-- Top-level dissector function for DAC packets.
--
-- This function is registered as a heuristic dissector, which means that it
-- will be called with info about each captured packet and must both decide
-- whether it knows how to analyze each packet, and also perform the analysis
-- if applicable. We check whether the packet is being sent to or from a DAC
-- board and then look up a dissector for the specific message type based on
-- the packet length. Returns the number of bytes dissected, or 0 for non-DAC
-- packets.
function p_dac.dissector(buf, pkt, root)
  if not (is_dac_mac(buf(0, 6)) or is_dac_mac(buf(6, 6))) then
    return 0
  end
  local data_len = buf:len() - 14
  local proto = dac_protos[data_len]
  if proto == nil then
    return 0
  end
  pkt.cols.protocol = "GHz DAC"
  local tree = root:add(p_dac, buf())
  tree:add(f_dac_dest, buf(0, 6))
  tree:add(f_dac_source, buf(6, 6))
  tree:add(f_dac_type, buf(12, 2))
  proto.dissector(buf(14, data_len):tvb(), pkt, root)
  return buf:len()
end


-- Top-level dissector function for ADC packets.
--
-- Works similarly to the DAC dissector above.
function p_adc.dissector(buf, pkt, root)
  if not (is_adc_mac(buf(0, 6)) or is_adc_mac(buf(6, 6))) then
    return 0
  end
  local data_len = buf:len() - 14
  local dst_mac = buf(0, 6)
  local src_mac = buf(6, 6)
  local proto = adc_protos[data_len]
  if proto == nil then
    return 0
  end
  pkt.cols.protocol = "GHz ADC"
  local tree = root:add(p_adc, buf())
  tree:add(f_adc_dest, buf(0, 6))
  tree:add(f_adc_source, buf(6, 6))
  tree:add(f_adc_type, buf(12, 2))
  proto.dissector(buf(14, data_len):tvb(), pkt, root)
  return buf:len()
end


-- Dissectors for specific DAC message types.
--
function p_dac_reg_write.dissector(buf, pkt, root)
  local tree = root:add(p_dac_reg_write, buf())
  tree:add(f_dac_start, buf(0, 1))
  tree:add(f_dac_readback, buf(1, 1))
end

function p_dac_reg_read.dissector(buf, pkt, root)
  local tree = root:add(p_dac_reg_read, buf())
end

function p_dac_sram_write.dissector(buf, pkt, root)
  local tree = root:add(p_dac_sram_write, buf())
end

function p_dac_jumptable_write.dissector(buf, pkt, root)
  local tree = root:add(p_dac_jumptable_write, buf())
end


-- Dissectors for specific ADC message types.
--
function p_adc_reg_write.dissector(buf, pkt, root)
  local tree = root:add(p_adc_reg_write, buf())
end

function p_adc_reg_read.dissector(buf, pkt, root)
  local tree = root:add(p_adc_reg_read, buf())
end

function p_adc_sram_write.dissector(buf, pkt, root)
  local tree = root:add(p_adc_sram_write, buf())
end

function p_adc_demod_output.dissector(buf, pkt, root)
  local tree = root:add(p_adc_demod_output, buf())
end

function p_adc_average_output.dissector(buf, pkt, root)
  local tree = root:add(p_adc_average_output, buf())
end


-- Register top-level DAC and ADC analysis functions as heuristic dissectors.
local ethertype_table = DissectorTable.get("ethertype")
p_dac:register_heuristic("eth", p_dac.dissector);
p_adc:register_heuristic("eth", p_adc.dissector);

