"""
Some tools
"""

import vtk
import sys

import numpy as np
from scipy import interpolate

import xml.etree.cElementTree as ET

from osgeo import gdal
from osgeo import osr
from osgeo import ogr

def setNumpyArrayValueToNaN(array, value):
    # for numpy array value to NaN if it equals to value
    array[array==value]=np.nan

    return array



def printProgressBar(i,total,postText):
    """A simple function to print a progress bar (no need to use other libraries)

    Note: any print inbetween the calling of this function will create a new progress bar. So
    it is better not print anything in between the calling.

    Reference:
    https://stackoverflow.com/questions/3002085/python-to-print-out-status-bar-and-percentage

    Parameters
    ----------
    i
    total
    postText

    Returns
    -------

    """
    n_bar =20 #size of progress bar
    j= (i+1)/total
    j=max(j,0.01001)  #at least print something at the beginning
    sys.stdout.write('\r')
    sys.stdout.write(f"[{'=' * int(n_bar * j):{n_bar}s}] {int(100 * j)}%  {postText}")
    sys.stdout.flush()

def build_gdal_vrt(vrtFileName, sourceGeoTiffFileNameList):
    """build GDAL VRT to compose terrain from multiple GeoTiff files

    Note: GDAL's earlier versions (<2.3.3) can't read BigTIFF files.

    It is an equivalent of the GDAL command: gdalbuildvrt result.vrt *.tif
    https://gdal.org/programs/gdalbuildvrt.html

    Attributes
    -------
    vrtFileName: {string} -- result VRT file name
    sourceGeoTiffFileNameList: {list} -- list of source GeoTiff file names

    Returns
    -------

    """

    vrt_options = gdal.BuildVRTOptions(resampleAlg='cubic', addAlpha=True)

    #result_vrt = gdal.BuildVRT(vrtFileName, sourceGeoTiffFileNameList, options=vrt_options)
    result_vrt = gdal.BuildVRT(vrtFileName, sourceGeoTiffFileNameList)

    #write the vrt to file
    result_vrt = None

def generate_custom_paraview_color_map(colorMapName, values, r, g, b):
    """ Generate custom color map for Paraview.

    The color map can be used have the same color scheme for the comparison e.g., SRH-2D (visualized in
    Paraview) and HEC-RAS (visualized in RAS Mapper).

    Example calling of this function:

    colorMapName = "HEC_RAS_Water_Depth"
    values = np.array([0, 3.75, 7.5, 11.25, 15])
    r = np.array([0, 0, 0, 0, 0]) / 255.0
    g = np.array([255, 191, 128, 64, 0]) / 255.0
    b = np.array([255, 226, 197, 168, 139]) / 255.0

    generate_custom_paraview_color_map(colorMapName, values, r, g, b)

    Attributes:
    colorMapName: {string} -- name of the color map and also the name of the created xml file
    values: {numpy 1D array} -- numpy 1D array for the values and range of the variable
    r: {numpy 1D array} -- numpy 1D array for red
    g: {numpy 1D array} -- numpy 1D array for green
    b: {numpy 1D array} -- numpy 1D array for blue

    Returns
    -------

    """

    # add new line after each element
    def indent(elem, level=0):
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for elem in elem:
                indent(elem, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    root = ET.Element("ColorMaps")

    ColorMap_depth = ET.SubElement(root, "ColorMap", name=colorMapName, space="RGB")
    for i in range(values.shape[0]):
        ET.SubElement(ColorMap_depth, "Point x=\" " + str(values[i]) + "\"  o=\"1\" " \
                      + "r=\"" + str(r[i]) + "\" " \
                      + "g=\"" + str(g[i]) + "\" " \
                      + "b=\"" + str(b[i]) + "\"").text = ""

    tree = ET.ElementTree(root)

    indent(root)

    # writing xml
    tree.write(colorMapName+"_colormaps.xml", encoding="utf-8", xml_declaration=True)

def generate_rating_curve_based_on_Mannings_equation(station_profile, zprofile, overboard,
                                                     station_ManningN, ManningN, slope,
                                                     number_of_rc_points, nResample=101, units='EN'):
    """ Generate a rating curve for a river cross section based on the Manning's equation

    The river corss section is given in (station, z) pair.

    The algorithm is an approximation. The whole profile is re-sampled on evenly distributed points (nResample). Then,
    each re-sampled subsection will calculate its area and wetted perimeter for a given stage. And then they are
    assembed into total areal and total wetted perimeter for use in the Manning's equation.

    The value of nResample determines the accuracy of the approximation.

    Parameters
    ----------
    station_profile: {numpy 1D array} -- numpy 1D array to store the station of points on the profile
    zprofile: {numpy 1D array} -- numpy 1D array to store the elevation of points on the profile
    overboard: {float} -- how much overboard above the maximum elevation of the profile
    station_ManningN: {numpy 1D array} -- numpy 1D array to store the station of points on the Manning's n profile
    ManningN: {numpy 1D array} -- numpy 1D array to store the Manning's n values of points on the profile
    slope: {float} -- slope at the cross section
    number_of_rc_points: {int} -- number of points on the rating curve
    units: {string} -- units used (either EN or SI)
    nResample: {int} -- optional number of resampling points on the profile. Default = 101 (i.e., 100 resampled segments)

    Returns
    -------
    stage: {numpy 1D array} -- numpy 1D array for stage
    Q: {numpy 1D array} -- numpy 1D array for discharge
    Area: {numpy 1D array} -- numpy 1D array for area
    Pwet: {numpy 1D array} -- numpy 1D array for wetted perimeter
    station_resample: {numpy 1D array} -- numpy 1D array for resampled station on the profile
    z_resample: {numpy 1D array} -- numpy 1D array for resampled elevation on the profile

    """

    #sanity check
    if station_profile.shape[0]!=zprofile.shape[0]:
        print("The lengths of arrays station and zprofile are different: ",
              station_profile.shape[0], zprofile.shape[0], ". Exiting ...")
        sys.exit()

    if station_ManningN.shape[0]!=ManningN.shape[0]:
        print("The lengths of arrays station_ManningN and ManningN are different: ",
              station_ManningN.shape[0], ManningN.shape[0], ". Exiting ...")
        sys.exit()

    # check the values in the array station_profile are strictly increasing
    bStationIncreasing = all(i < j for i, j in zip(station_profile, station_profile[1:]))

    if not bStationIncreasing:
        print("Values in station_profile are not strictly increasing. Check. Exiting ...")
        sys.exit()

    # check the values in the array station_ManningN are strictly increasing
    bStationIncreasing = all(i < j for i, j in zip(station_ManningN, station_ManningN[1:]))

    if not bStationIncreasing:
        print("Values in station_ManningN are not strictly increasing. Check. Exiting ...")
        sys.exit()

    if (ManningN<=0).all() or slope<=0 or number_of_rc_points<=0:
        print("Manning's n, slope, and number_of_rc_points can't be negative or zero. Exiting ...")
        sys.exit()

    if units!="EN" and units!="SI":
        print("Specified units must be either EN or SI. The current units are not valid: ", units)
        sys.exit()

    #unit factor (default is SI)
    Kn = 1.0

    if units=="EN":
        Kn = 1.486

    Q = np.zeros(number_of_rc_points)
    zmin = np.min(zprofile)   #min of profile elevation
    zmax = np.max(zprofile)   #max of profile elevation
    stage = np.linspace(zmin, zmax+overboard, number_of_rc_points)

    station_resample = np.linspace(0, np.max(station_profile), nResample)

    #station distance between re-sample points
    dx_resample = (np.max(station_profile) - np.min(station_profile)) /(nResample-1)

    #interplate the channel profile and Manning's n to the re-sampling points
    profile_interpolator = interpolate.interp1d(station_profile, zprofile)
    ManningN_interpolator = interpolate.interp1d(station_ManningN, ManningN)

    z_resample = profile_interpolator(station_resample)

    n_resample = ManningN_interpolator(station_resample)

    #now each re-sampled section is a trazoidal with
    #1. two points on top: (station_resample[i], zmax), (station_resample[i+1], zmax)
    #2. two points on bottom: (station_resample[i], z_resample[i]), (station_resample[i+1], z_resample[i+1])

    #area and wetted perimenter vs. depth
    Area = np.zeros(number_of_rc_points)
    Pwet = np.zeros(number_of_rc_points)

    #loop over different stage on the rating curve
    for pointI in range(number_of_rc_points):
        #get the current stage
        current_stage = stage[pointI]  #current constant stage

        # list of 0 or 1 to signify whether a re-sampled section (i, i+1) is wetted or not
        # a section is wetted only when both bottom points are below the free surface
        underWaterFlag = np.zeros(nResample - 1)

        #loop over all re-sampled sections
        for sectionI in range(nResample-1):
            #the current re-sampled section is wet only when both bottom points are below the stage
            if z_resample[sectionI] < current_stage and z_resample[sectionI+1] < current_stage:
                underWaterFlag[sectionI] = 1

        #accumulate area and wetted perimeter
        for sectionI in range(nResample-1):
            Area[pointI] += 0.5*( (current_stage-z_resample[sectionI]) + (current_stage-z_resample[sectionI+1]))* \
                            dx_resample*underWaterFlag[sectionI]

            Pwet[pointI] += np.sqrt( dx_resample**2 + (z_resample[sectionI]-z_resample[sectionI+1])**2 )*underWaterFlag[sectionI]


        #now we have the total area and wetted perimenter, we can use the Manning's equation to get discharge Q
        #if all re-sampled profile points are above water, discharge is zero.
        if np.max(underWaterFlag) <= 0:
            Q[pointI] = 0.0
        else:
            Q[pointI] = Kn/n_resample[pointI]*Area[pointI]*\
                        (Area[pointI]/Pwet[pointI])**(2.0/3.0)*np.sqrt(slope)

    return stage, Q, Area, Pwet, station_resample, z_resample