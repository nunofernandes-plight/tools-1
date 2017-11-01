#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue May 24 16:18:39 2016

@author: raphaelproux

This library allows to read SPE3 files generated by Princeton Instruments Lightfield software.

This is a python 3 library tested with python 3.6 - RProux 17/10/2017


IMPORTANT NOTE: needs the xmltodict package to work. 
If not installed install it using PIP typing "pip install xmltodict" in a terminal

"""
import pylab as pl
import xmltodict

class SPE3map:

    """Class which handles the reading of SPE3 files.

    Reliable attributes (standardized interface): data, exposureTime, nbOfFrames, regionSize, SPEversion and wavelength.
    
    Attributes:
        data (numpy array): numpy array containing the frames
        DATAOFFSET (int): offset to the binary data is fixed (4100 bytes) in SPE 2.X/3 file format
        dataType (short): experiment datatype (0 = float (4 bytes), 1 = long (4 bytes), 2 = short (2 bytes), 3 = unsigned short (2 bytes))
        exposureTime (float): exposure time of each frame in seconds
        fname (str): filename
        frameSize (int): size in bytes of a frame in the records
        frameStride (int): step in bytes from one record to the next
        nbOfFrames (int): number of frames recorded in the file
        regionSize (tuple): size of a frame (nb of pixels along y (1 for a simple spectrum), nb of pixels along x)
        SPEversion (float): SPE version of the file (should be 2.xxx)
        SPEVERSIONOFFSET (int): offset in bytes where to read the SPE version in the file
        wavelength (numpy array): array of floats containing the wavelengths vector read from the file.
        XMLFOOTEROFFSETPOS (int): position in bytes giving the offset to the XML footer (UnsignedInteger64)
    """
    
    SPEVERSIONOFFSET = 1992  # offset for obtaining SPE version (float32)    
    XMLFOOTEROFFSETPOS = 678  # position in bytes giving the offset to the XML footer (UnsignedInteger64)
    DATAOFFSET = 4100  # offset to the binary data is fixed (4100 bytes) in SPE 2.X/3 file format
    
    def __init__(self, fname = None, fid = None):
        """
        This function initializes the class and, if either a filename or fid is
            provided, opens the datafile and reads the contents.

        Parameters:
            fname (str, optional): Filename of SPE file
            fid (file, optional): File ID object of open stream (NOTE: never tested)
        """
        
        self._fid = None
        self.fname = fname
        if fname is not None:
            self.openFile(fname)
        elif fid is not None:
            self._fid = fid

        if self._fid:
            self.readData()
            self._fid.close()
            
    def readData(self):
        """Read all the data into the class"""
        self._readSPEversion()
        try:
            assert(self.SPEversion >= 3)# or print 'This file is not a SPE 3.x file.'
        except:
            raise
#            print 'This program should be used only with SPE3.x files and higher. The file given has a {} version number.'.format(self.SPEversion)
        self._readXMLfooter()
        self._readWavelengths()
        self._readFramesInfo()
        self._readRegionSize()
        self._readExposureTime()
        self._readArray()
        
    def openFile(self, fname):
        """Open a SPE file
        
        Args:
            fname (str): filename
        """
        self._fname = fname
        self._fid = open(fname, "rb")

    def _readAtNumpy(self, pos, size, ntype):
        """Reads a number from the file.
        
        Args:
            pos (int): Position in the file in bytes
            size (int): Number of elements to read (-1 for all items)
            ntype (data-type): Type of number (number of bytes to read = sizeof(ntype) * size)
        
        Returns:
            number or numpy array: numpy array of read numbers if several numbers (size > 1). Simple number otherwise.
        """
        self._fid.seek(pos)
#        print(ntype, type(ntype), size, type(size))
        return pl.fromfile(self._fid, ntype, int(size))
        
    def _readSPEversion(self):
        """Determines SPE file version (always there in SPE 2.x or 3.0 files)"""
        self.SPEversion = self._readAtNumpy(self.SPEVERSIONOFFSET, 1, pl.float32)[0]
        
    def _readXMLfooter(self):
        """Extracts the XML footer and puts it in _footerInfo as an ordered dictionnary (cf. xmltodict package)"""
        XMLfooterPos = self._readAtNumpy(self.XMLFOOTEROFFSETPOS, 1, pl.uint64)[0]
        self._fid.seek(XMLfooterPos)
        self._footerInfo = xmltodict.parse(self._fid.read())

    def _readWavelengths(self):
        """Extracts the wavelength vector determined by spectrometer calibration"""
        wavelengthStr = self._footerInfo['SpeFormat']['Calibrations']['WavelengthMapping']['Wavelength']['#text']
        self.wavelength = pl.array([float(w) for w in wavelengthStr.split(',')])
        
    def _readFramesInfo(self):
        """Extracts frames info from XML footer (number of frames, data type, frame size, frame stride)
        MUST BE CALLED AFTER _readXMLfooter()"""
        assert(self._footerInfo['SpeFormat']['DataFormat']['DataBlock']['@type'] == 'Frame')
        self.nbOfFrames = int(self._footerInfo['SpeFormat']['DataFormat']['DataBlock']['@count'])
        dataTypeName = self._footerInfo['SpeFormat']['DataFormat']['DataBlock']['@pixelFormat']
        possibleDataTypes = {'MonochromeUnsigned16': pl.uint16,
                             'MonochromeUnsigned32': pl.uint32,
                             'MonochromeFloat32': pl.float32,
                             'MonochromeFloating32': pl.float32}
        self.dataType = possibleDataTypes[dataTypeName]
        self.frameSize = int(self._footerInfo['SpeFormat']['DataFormat']['DataBlock']['@size'])
        self.frameStride = int(self._footerInfo['SpeFormat']['DataFormat']['DataBlock']['@stride'])
        
    def _readRegionSize(self):
        """Extracts width and height of the region of interest
        MUST BE CALLED AFTER _readXMLfooter()"""
        assert(self._footerInfo['SpeFormat']['DataFormat']['DataBlock']['DataBlock']['@type'] == 'Region')
        height = int(self._footerInfo['SpeFormat']['DataFormat']['DataBlock']['DataBlock']['@height'])
        width = int(self._footerInfo['SpeFormat']['DataFormat']['DataBlock']['DataBlock']['@width'])
        self.regionSize = (height,width)
        
    def _readExposureTime(self):
        """Extracts the camera exposure time
        MUST BE CALLED AFTER _readXMLfooter()"""
        self.exposureTime = float(self._footerInfo['SpeFormat']['DataHistories']['DataHistory']['Origin']['Experiment']['Devices']['Cameras']['Camera']['ShutterTiming']['ExposureTime']['#text'])
        
    def _readArray(self):
        """Reads the binary data contained in the file"""
        self.data = []
        for frameNb in range(self.nbOfFrames):
            frameData = self._readAtNumpy(self.DATAOFFSET + frameNb * self.frameStride, self.frameSize / self.dataType().nbytes, self.dataType)
            self.data.append(frameData.reshape(self.regionSize))
        self.data = pl.array(self.data)
        
    def saveXMLinfo(self, filePath):
        """allows the user to save the XML footer to a file of his choice
        
        Args:
            filePath (str): filename of the XML file where to save the header.
        """
        text_file = open(filePath, "w")
        text_file.write(xmltodict.unparse(self._footerInfo))
        text_file.close()


if __name__ == "__main__":
    from tkinter.filedialog import askopenfilename
    from tools.arrayProcessing import range_to_edge, filter_cosmic_rays
    import glob, os

    os.chdir(r"/Users/raphaelproux/Desktop/mocvd-wse2/170904-4K-good-map/power-dep/")
    pl.figure()
    powers = []
    spectra = []
    signals = []
    for filename in glob.glob("*.spe"):
        data = SPE3map(filename)
        spectrum = data.data[0][0].astype(pl.uint32)
        
        spectrum = filter_cosmic_rays(spectrum, filter_size=7)
#        spectrum = (spectrum - pl.mean(spectrum[0:50])) / (data.exposureTime / 1000)
        
        spectra.append(spectrum)
        
        power, _ = os.path.splitext(filename)
        powers.append(float(power) * 5000)  # power in microwatts
        signals.append(pl.sum(spectrum))
        pl.plot(data.wavelength, spectrum / signals[-1], label=r'${}\ \mu W$'.format(powers[-1]))
        
#        pl.savetxt('{}.txt'.format(powers[-1]), pl.array([data.wavelength, spectrum / signals[-1]]).transpose())
        
    pl.legend()
    pl.figure()
    pl.plot(powers, signals, 'o')
    m, p = pl.polyfit(powers, signals, 1)
    pl.plot(powers, m * pl.array(powers) + p)
    pl.xlabel('Power ($\mu W$)')
    pl.ylabel('Counts per second')
    
    print('linear fit:', m,'x signal +', p)

#    pl.savetxt('sat_curve.txt', pl.array([powers, signals]).transpose())
    
    