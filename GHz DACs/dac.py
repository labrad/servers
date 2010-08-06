
DAC_SRAM_LEN = 10240 #words
DAC_SRAM_PAGE_LEN = 256 #words
DAC_SRAM_PAGES = DAC_SRAM_LEN/DAC_SRAM_PAGE_LEN
DAC_SRAM_DTYPE = np.uint8

class DACProxy(object):
    """ Represents a GHzDAC board.
    ATTRIBUTES
    sram - numpy array representing the board's SRAM.
        each element is of type <u4, meaning little endian, four bytes.
    """
    def __init__(self, mac, adapter):
        self.mac = mac
        self.adapter = adapter
        adapter.addListener(self)
        self.sram = np.zeros(DAC_SRAM_LEN, dtype=DAC_SRAM_DTYPE)
        self.register = np.zeros(DAC_REG_BYTES)

    def __call__(self, packet):
        """Handle an incoming ethernet packet to this board"""
        src, dest, typ, data = packet
        if dest != self.mac:
            return
        if len(data) == DAC_SRAM_PACKET_LENGTH:
            self.handle_sram_packet(packet)
        elif len(data) == REG_PACKET_LENGTH:
            self.handle_register_packet(packet)
        else:
            raise Exception('GHzDAC packet length not appropriate for register or SRAM')

    def handle_sram_packet(self, packet):
        """Stores SRAM data from a packet in the device's SRAM.

        PARAMETERS
        packet - numpy array of 

        SRAM packets have 256 words, each word is 32 bits long (4 bytes)
        One word represents 1 ns of sequence data.
        Each word has 14 bits for each DAC channel, plus four bits for the four ECL triggers (=32 bits).
        Each byte has the following form:
            bits[13..0] = DACA[13..0] D/A converter A
            bits[13..0] = DACB[13..0] D/A converter B
            bits[31..28]= SERIAL[3..0] ECL serial output
        """
        