import logging
import qt
import vtk
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import numpy as np
import random
import os
import json


#Restores Layout after saving in mrml file
def _restoreCustomLayout(caller, event):

  layoutNode = slicer.util.getNode('*LayoutNode*')
  paramNode = slicer.mrmlScene.GetSingletonNode(
    'SegmentationVerification', 'vtkMRMLScriptedModuleNode')
  if not paramNode:
     return

  xml_code = paramNode.GetParameter("LayoutXML")
  if xml_code:
    layoutNode = slicer.util.getNode('*LayoutNode*')
    userViewId = layoutNode.SlicerLayoutUserView
    if layoutNode.IsLayoutDescription(userViewId):
      layoutNode.SetLayoutDescription(userViewId, xml_code)
    else:
      layoutNode.AddLayoutDescription(userViewId, xml_code)
    layoutNode.SetViewArrangement(userViewId)

slicer.mrmlScene.AddObserver(slicer.mrmlScene.EndImportEvent, _restoreCustomLayout)

#
# SegmentationVerification
#
class SegmentationVerification(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Segmentation Verification"
    self.parent.categories = ["Segmentation"]
    self.parent.dependencies = []
    self.parent.contributors = ["Csaba Pinter (EBATINCA)"]
    self.parent.helpText = """
This module allows manual revision of segments in a user friendly manner.
"""
    self.parent.acknowledgementText = """
This file was originally developed by Csaba Pinter (EBATINCA), with no funding.
"""


#
# SegmentationVerificationWidget
#
class SegmentationVerificationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)  # needed for parameter node observation
    self.logic = None
    self._parameterNode = None
    self._updatingGUIFromParameterNode = False
    self._segmentationVolumeMap = {}
    base_path = os.path.dirname(os.path.abspath(__file__))
    self._icons = {
        'header_visible': qt.QIcon(os.path.join(base_path, "Resources", "Icons", "SlicerVisibleInvisible.png")),
        'header_color'  : qt.QIcon(os.path.join(base_path, "Resources", "Icons", "SlicerAddTransform.png")),
        'visible'       : qt.QIcon(os.path.join(base_path, "Resources", "Icons", "SlicerVisible.png")),
        'invisible'     : qt.QIcon(os.path.join(base_path, "Resources", "Icons", "SlicerInvisible.png")),
    }
    self.setUp = False


  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/SegmentationVerification.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)
    self.ui.volumeNodeComboBox.setMRMLScene(slicer.mrmlScene)
    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = SegmentationVerificationLogic()

    #Creates a Mapping Volumes -> Segmentation Files (Everytime a new segmentation node or volume is added it updates)
    self._buildSegmentationVolumeMap()
    self._segmentGroupMapping = {}
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.NodeAddedEvent, self._buildSegmentationVolumeMap)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.NodeRemovedEvent, self._buildSegmentationVolumeMap)

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    #Connections for the Segmentation Verification part of the Module
    self.ui.segmentationNodeComboBox.currentNodeChanged.connect(self.onSegmentationChanged)

    self.ui.showNeighborsCheckBox.clicked.connect(self.updateParameterNodeFromGUI)
    self.ui.nextButton.clicked.connect(self.onNextButton)
    self.ui.previousButton.clicked.connect(self.onPreviousButton)
    
    #Connections for the Segmentation Comparison part of the Module
    #Dialog for the Segmentation Model Keywords
    self.segModelDialog = slicer.util.loadUI(self.resourcePath('UI/SegModelsDialog.ui'))
    self.dialogUi = slicer.util.childWidgetVariables(self.segModelDialog)
    self.segModelDialog.hide()

    self.ui.openModelButton.clicked.connect(self.showSegModelDialog)
    self.dialogUi.okTableButton.clicked.connect(lambda checked=False: self.segModelDialog.accept())

    self.dialogUi.addRowButton.clicked.connect(self.onAddRow)
    self.dialogUi.deleteRowButton.clicked.connect(self.onDeleteRow)
    self.dialogUi.modelNametableWidget.itemChanged.connect(self.onModelTableItemChanged)

    #Dialog for the Segmentaion Goup Keywords
    self.segGroupDialog = slicer.util.loadUI(self.resourcePath('UI/SegGroupsDialog.ui'))
    self.dialogGroupUi = slicer.util.childWidgetVariables(self.segGroupDialog)
    self.segGroupDialog.hide()

    self.ui.openGroupButton.clicked.connect(self.showSegGroupDialog)
    self.dialogGroupUi.okTableButton.clicked.connect(lambda checked=False: self.segGroupDialog.accept())

    self.dialogGroupUi.addGrouptable.itemChanged.connect(self.onGroupTableItemChanged)
    self.dialogGroupUi.addRowButton.clicked.connect(self.onAddRowGroup)
    self.dialogGroupUi.deleteRowButton.clicked.connect(self.onDeleteRowGroup)

    #Connections for Model and Segmentation Connection
    self.ui.volumeNodeComboBox.currentNodeChanged.connect(self.onVolumeChanged)
    self.ui.ModelCheckableComboBox.checkedIndexesChanged.connect(self.onModelChanged)
    self.ui.SegmentationsCheckableComboBox.checkedIndexesChanged.connect(self.onModelChanged)

    #Connections for the Layout Selection
    self.ui.threedCheckbox.clicked.connect(self.updateLayout)
    self.ui.twodCheckbox.clicked.connect(self.updateLayout)
    self.ui.checkBoxVertical.clicked.connect(self.updateLayout)

    #Connections for the Options Collapsible Button
    self.ui.link3DViewCheckBox.clicked.connect(self.onLinkThreeDViewChanged)
    self.ui.link2DViewCheckBox.clicked.connect(self.onLinkTwoDViewChanged)
    self.ui.outlineCheckBox.clicked.connect(self.onFillingOutlineChanged)

    #Connections for the Segment by Segment Collapsible Button
    self.ui.segmentGroupComboBox.currentIndexChanged.connect(self.onSegmentGroupChanged)
    self.ui.showNeighboringcheckBoxMultiple.clicked.connect(self.updateParameterNodeFromGUI)

    self.ui.SegmentsTableView.selectionChanged.connect(self.onSegmentSelectionChanged)
    #self.ui.segmentationTableWidget.selectionModel().selectionChanged.connect(self.onSegmentSelectionChangedMultiple)
    self.ui.segmentationTableWidget.cellClicked.connect(self.onSegmentSelectionChangedMultiple)

    self.ui.nextButton_comparison.clicked.connect(self.onNextButtonMultiple)
    self.ui.previousButton_comparison.clicked.connect(self.onPreviousButtonMultiple)

    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def enter(self):
    """
    Called each time the user opens this module.
    """
    # Make sure parameter node exists and observed
    self.initializeParameterNode()

  def exit(self):
    """
    Called each time the user opens a different module.
    """
    # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
    self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

  def onSceneStartClose(self, caller, event):
    """
    Called just before the scene is closed.
    """
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)

  def onSceneEndClose(self, caller, event):
    """
    Called just after the scene is closed.
    """
    # If this module is shown while the scene is closed then recreate a new parameter node immediately
    if self.parent.isEntered:
      self.initializeParameterNode()

  def initializeParameterNode(self):
    """
    Ensure parameter node exists and observed.
    """
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.
    self.setParameterNode(self.logic.getParameterNode())

  def setParameterNode(self, inputParameterNode):
    """
    Set and observe parameter node.
    Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
    """
    if inputParameterNode:
      self.logic.setDefaultParameters(inputParameterNode)

    # Unobserve previously selected parameter node and add an observer to the newly selected.
    # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
    # those are reflected immediately in the GUI.
    if self._parameterNode is not None:
      self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    self._parameterNode = inputParameterNode
    if self._parameterNode is not None:
      self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    # Initial GUI update
    self.updateGUIFromParameterNode()

  def updateGUIFromParameterNode(self, caller=None, event=None):
    """
    This method is called whenever parameter node is changed.
    The module GUI is updated to show the current state of the parameter node.
    """
    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    self._updatingGUIFromParameterNode = True

    #Set Selected Segmentation Node in Segmentation Verification and Selected Volume Node in Segmentation Comparison
    self.ui.segmentationNodeComboBox.setCurrentNode(self._parameterNode.GetNodeReference("CurrentSegmentationNode"))
    self.ui.volumeNodeComboBox.setCurrentNode(self._parameterNode.GetNodeReference("CurrentVolumeNode"))

    #Update all Checkboxes based on the Value saved in the parameter Node
    checkboxMapping = {
        "ShowNeighbors":       self.ui.showNeighborsCheckBox,
        "ShowNeighborsMultiple": self.ui.showNeighboringcheckBoxMultiple,
        "Show3D":              self.ui.threedCheckbox,
        "Show2D":              self.ui.twodCheckbox,
        "VerticalLayout":      self.ui.checkBoxVertical,
        "3DLink":              self.ui.link3DViewCheckBox,
        "2DLink":              self.ui.link2DViewCheckBox,
        "OutlineRep":          self.ui.outlineCheckBox,
    }
    for key, widget in checkboxMapping.items():
        val = self._parameterNode.GetParameter(key)
        if val is not None:
            widget.setChecked(val == "True")

    #Only called once in the beginning to set up the scene after Reloading, saving or initialization
    if not self.setUp:
      self.setUp = True
      self.setupOptions()

    #Changes the table selection based on the parameter Node
    self._changeTableSelection()

    # All the GUI updates are done
    self._updatingGUIFromParameterNode = False

  def setupOptions(self):
    """
    Initiliazes the Layout and the Funktions based on the values in the Parameter Node once after opening the Module
    """
    self.onVolumeChanged()
    #Set the Layout of the Pop up tables
    self._setupModelGroupTable()

    #Get Checked Segmentation IDs -> To restore Checked Segmentations from the parameter Node
    segmentationIDsString = self._parameterNode.GetParameter("SegmentationIDs") or ""
    if segmentationIDsString:
        selectedSegIds = segmentationIDsString.split(";")
    else:
        selectedSegIds = []

    #Get Checked Model IDS -> To restore Checked Segmentation Models from the parameter Node
    modelIDsString = self._parameterNode.GetParameter("ModelIDs") or ""
    if modelIDsString:
        selectedIds = modelIDsString.split(",")
    else:
        selectedIds = []

    #Get the Name of the Segmentation Group saved in the parameter node
    savedGroup = self._parameterNode.GetParameter("SelectedGroup")

    #Set up the Segmentations Combo Box
    
    #Check Segmentations in the Segmentations Combo Box based on the Segmentation IDs from the parameter node
    comboSegmentations = self.ui.SegmentationsCheckableComboBox.model()
    for row in range(comboSegmentations.rowCount()):
        item = comboSegmentations.item(row)
        itemID = item.text()
        if itemID in selectedSegIds:
            item.setCheckState(qt.Qt.Checked)
        else:
            item.setCheckState(qt.Qt.Unchecked)

    # Set up the Segmentation Model Combo Box and the Table in the pop up Dialog to fill the Segmentation Model Combo Box
    
    #Modelnames are based on the pop up table for Segmentation Models
    #When segmentation models are saved in the Parameternode (e.g., after saving a scene they are loaded)
    #Otherwise for e.g. after opening a new slicer instance the Mapping is loaded from the registry files -> Should reduce the effort to type in the Keywords every time
    mapping_json = self._parameterNode.GetParameter("ModelKeywordMapping")
    if not mapping_json:
       settings = qt.QSettings()
       mapping_json = settings.value("SegmentationVerification/ModelKeywordMapping", "") or "{}"
    
    #Write the pre-saved Modelnames and the Keyword in the table in the pop up
    #Through the connections the funktion to load the Models in the Combo Box is called automatically here
    mapping = json.loads(mapping_json)
    table = self.dialogUi.modelNametableWidget
    table.clearContents()
    table.setRowCount(0)
    for model, keywords in mapping.items():
        row = table.rowCount
        table.insertRow(row)
        table.setItem(row, 0, qt.QTableWidgetItem(model))
        table.setItem(row, 1, qt.QTableWidgetItem(",".join(keywords)))
    
    #Check Segmentation Models in the Segmentation Model Combo Box based on the Segmentation IDs from the parameter node
    comboModel = self.ui.ModelCheckableComboBox.model()
    for row in range(comboModel.rowCount()):
        item = comboModel.item(row)
        itemID = item.text()
        if itemID in selectedIds:
            item.setCheckState(qt.Qt.Checked)
        else:
            item.setCheckState(qt.Qt.Unchecked)
    
    #Groupnames are based on the pop up table for Segmentation Groups
    #When segmentation groups are saved in the Parameternode (e.g., after saving) a scene they are loaded
    #Otherwise for e.g. after opening a new slicer instance the Mapping is loaded from the registry files -> Should reduce the effort to type in the Keywords every time
    group_mapping_json = self._parameterNode.GetParameter("GroupKeywordMapping")
    if not group_mapping_json:
       settings = qt.QSettings()
       group_mapping_json = settings.value("SegmentationVerification/GroupKeywordMapping", "") or "{}"

    #Write the pre-saved Groupnames and the Keyword in the table in the pop up
    #Through the connections the function to load the Segment Groups in the Combo Box is called automatically here
    mapping = json.loads(group_mapping_json)
    table = self.dialogGroupUi.addGrouptable
    table.clearContents()
    table.setRowCount(0)
    for model, keywords in mapping.items():
        row = table.rowCount
        table.insertRow(row)
        table.setItem(row, 0, qt.QTableWidgetItem(model))
        table.setItem(row, 1, qt.QTableWidgetItem(",".join(keywords)))
    
    #Select the saved Segmentation Group
    combo = self.ui.segmentGroupComboBox
    idx = combo.findText(savedGroup)
    combo.setCurrentIndex(idx if idx >= 0 else 0)

    #Initiliaze the Layout of the Segmentation Table in the Segment by Segment Collapsible Button
    self.configure_table()
    #Based on the Segmentation/Model Selection and the Checkboxes enable the options
    self.enableOptions((self._parameterNode.GetParameter("Show3D")), (self._parameterNode.GetParameter("Show2D")))
    #Based on the Selected Group update the showed Segments in the Group and the Segment Table 
    self.onSegmentGroupChanged()


  def _setupModelGroupTable(self):
    """
    Initilializes the Layout for the two tables in the pop up dialog (Segmentation Group and Segmentation Model)
    """
    table_model = self.dialogUi.modelNametableWidget
    self.logic.setupAddTables(table_model,["Modelnames", "Keywords"] )
    
    table_group = self.dialogGroupUi.addGrouptable
    self.logic.setupAddTables(table_group,["Groupnames", "Keywords"] )

  def _changeTableSelection(self):
    """
    Selects the segment that is saved in the parameter node if the segment is part of the Segment Table
    When the Segment is not part of the Table reset the segment Group
    """
    tableName = self._parameterNode.GetParameter("VerificationTableSelection")
    self.ui.segmentationTableWidget.clearSelection()
    found = False

    if tableName:
      table = self.ui.segmentationTableWidget
      for row in range(table.rowCount):
          item = table.item(row, 3)
          if item and item.text() == tableName:
              table.selectRow(row)
              found = True
              break
    if not tableName or not found:
       self.onSegmentGroupChanged()
     
  def configure_table(self):
    """
    Update/Setup Table Layout -> Load Icons etc.
    """
    table = self.ui.segmentationTableWidget
    table.clearContents()
    #5 colums
    table.setColumnCount(5)
    #Icons for header
    headers = [
        ( self._icons['header_visible'], ""),
        (self._icons['header_color'], ""),
        (None, "Opacity"),  
        (None, "Name"),  
        (None, "Number of Segmentations") 
    ]
    #Set colum header
    for col, (icon, text) in enumerate(headers):
        item = qt.QTableWidgetItem(icon, text) if icon else qt.QTableWidgetItem(text)
        table.setHorizontalHeaderItem(col, item)
    hdr = table.horizontalHeader()
    for c in (0, 1, 2, 4):
        hdr.setSectionResizeMode(c, qt.QHeaderView.ResizeToContents)
    hdr.setSectionResizeMode(3, qt.QHeaderView.Stretch)
    table.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAlwaysOff)
    hdr.setVisible(True)

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

    self._parameterNode.SetNodeReferenceID("CurrentSegmentationNode", self.ui.segmentationNodeComboBox.currentNodeID)
    self._parameterNode.SetNodeReferenceID("CurrentVolumeNode", self.ui.volumeNodeComboBox.currentNodeID)

    self._parameterNode.SetParameter("ShowNeighbors", 'True' if self.ui.showNeighborsCheckBox.checked else 'False')
    self._parameterNode.SetParameter("ShowNeighborsMultiple", 'True' if self.ui.showNeighboringcheckBoxMultiple.checked else 'False')

    selectedIds = [ index.data() for index in self.ui.ModelCheckableComboBox.checkedIndexes() ]
    self._parameterNode.SetParameter("ModelIDs", ",".join(selectedIds))

    selectedSegmentationIds = [ index.data() for index in self.ui.SegmentationsCheckableComboBox.checkedIndexes() ]
    self._parameterNode.SetParameter("SegmentationIDs", ";".join(selectedSegmentationIds))

    self._parameterNode.SetParameter("Show3D", "True" if self.ui.threedCheckbox.checked else "False")
    self._parameterNode.SetParameter("Show2D", "True" if self.ui.twodCheckbox.checked else "False")
    self._parameterNode.SetParameter("VerticalLayout", "True" if self.ui.checkBoxVertical.checked else "False")
    self._parameterNode.SetParameter("3DLink", "True" if self.ui.link3DViewCheckBox.checked else "False")
    self._parameterNode.SetParameter("2DLink", "True" if self.ui.link2DViewCheckBox.checked else "False")
    self._parameterNode.SetParameter("OutlineRep", "True" if self.ui.outlineCheckBox.checked else "False")
    self._parameterNode.SetParameter("SelectedGroup", self.ui.segmentGroupComboBox.currentText)
    sel = self.ui.segmentationTableWidget.selectedItems()
    if not sel:
        return

    selected_row = sel[0].row()
    name = self.ui.segmentationTableWidget.item(selected_row, 3).text()

    self._parameterNode.SetParameter("VerificationTableSelection", name)

    self._parameterNode.EndModify(wasModified)


  #Function used in the Segmentation Verification Collapsible Button

  def onSegmentationChanged(self, newSegmentationNode):
    """
    Switch to next segment.
    """
    if newSegmentationNode:
      self._parameterNode.SetNodeReferenceID("CurrentSegmentationNode", newSegmentationNode.GetID())
    else:
      self._parameterNode.SetNodeReferenceID("CurrentSegmentationNode", "")
      return

    # Set wait cursor
    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)

    # Make sure segmentation is shown in 3D
    newSegmentationNode.CreateClosedSurfaceRepresentation()

    self.logic.initializeSegmentBoundingBoxes(self._parameterNode)

    # Enable next button but disable previous button until next is clicked
    self.ui.nextButton.setEnabled(True)
    self.ui.previousButton.setEnabled(False)

    qt.QApplication.restoreOverrideCursor()

  def onNextButton(self):
    """
    Switch to next segment.
    """
    segmentationNode = self._parameterNode.GetNodeReference("CurrentSegmentationNode")
    if not segmentationNode:
      raise ValueError("No segmentation node is selected")

    # Get next segment ID
    selectedSegmentIDs = self.ui.SegmentsTableView.selectedSegmentIDs()
    if len(selectedSegmentIDs) == 0:
      nextSegmentID = self.ui.SegmentsTableView.segmentIDForRow(0)
      logging.info(f'Selecting segment at row 0 (ID: {nextSegmentID})')
    else:
      selectedSegmentID = selectedSegmentIDs[0]
      nextRowIndex = self.ui.SegmentsTableView.rowForSegmentID(selectedSegmentID) + 1
      if nextRowIndex >= self.ui.SegmentsTableView.segmentCount:
        raise RuntimeError("There is no next segment")
      nextSegmentID = self.ui.SegmentsTableView.segmentIDForRow(nextRowIndex)
      logging.info(f'Selecting segment at row {nextRowIndex} (ID: {nextSegmentID})')

    # Select next segment
    self.ui.SegmentsTableView.setSelectedSegmentIDs([nextSegmentID])
    segmentationNode.GetDisplayNode().Modified()  # Workaround to make sure visibilities are updated

  def onPreviousButton(self):
    """
    Switch to previous segment.
    """
    segmentationNode = self._parameterNode.GetNodeReference("CurrentSegmentationNode")
    if not segmentationNode:
      raise ValueError("No segmentation node is selected")

    # Get previous segment ID
    selectedSegmentIDs = self.ui.SegmentsTableView.selectedSegmentIDs()
    if len(selectedSegmentIDs) == 0:
      previousSegmentID = self.ui.SegmentsTableView.segmentIDForRow(self.ui.SegmentsTableView.segmentCount - 1)
      logging.info(f'Selecting segment at row {self.ui.SegmentsTableView.segmentCount - 1} (ID: {previousSegmentID})')
    else:
      selectedSegmentID = selectedSegmentIDs[0]
      previousRowIndex = self.ui.SegmentsTableView.rowForSegmentID(selectedSegmentID) - 1
      if previousRowIndex < 0:
        raise RuntimeError("There is no previous segment")
      previousSegmentID = self.ui.SegmentsTableView.segmentIDForRow(previousRowIndex)
      logging.info(f'Selecting segment at row {previousRowIndex} (ID: {previousSegmentID})')

    # Select previous segment
    self.ui.SegmentsTableView.setSelectedSegmentIDs([previousSegmentID])
    segmentationNode.GetDisplayNode().Modified()  # Workaround to make sure visibilities are updated

  def onSegmentSelectionChanged(self):
    selectedSegmentIDs = self.ui.SegmentsTableView.selectedSegmentIDs()
    if len(selectedSegmentIDs) == 0 or len(selectedSegmentIDs) > 1:
      return
    selectedSegmentID = selectedSegmentIDs[0]

    # Set wait cursor
    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)

    # Update next/previous button enabled state
    currentRowIndex = self.ui.SegmentsTableView.rowForSegmentID(selectedSegmentID)
    self.ui.nextButton.enabled = (currentRowIndex < self.ui.SegmentsTableView.segmentCount - 1)
    self.ui.previousButton.enabled = (currentRowIndex > 0)

    # Perform segment selection
    self.logic.selectSegment(self._parameterNode, selectedSegmentID)

    qt.QApplication.restoreOverrideCursor()



  #Function used in the Segmentation Comparison Collapsible Button

  def _buildSegmentationVolumeMap(self, caller=None, event=None):
    """
    Creates a global dict that maps Segmentation files to their corresponding Volume
    Is updated everytime a new volume or segmentation is loaded into slicer
    First called during the set up after opening the module
    """
    self._segmentationVolumeMap.clear()
    for seg in slicer.util.getNodesByClass('vtkMRMLSegmentationNode'):
        volRef = seg.GetNodeReference(seg.GetReferenceImageGeometryReferenceRole())
        if volRef:
            self._segmentationVolumeMap.setdefault(volRef.GetID(), []).append(seg)


  #Funktions for the pop up/Dialog for the Keyword Tables

  #Functions for the Segmentation Model Keyword Table
  def showSegModelDialog(self):
    """
    Executes the Dialog/pop up to the Segmentation Model Keyword Table
    Called on clicking the + Button next to the Combo Box
    """
    self.segModelDialog.exec_()

  def onModelTableItemChanged(self):
    """
    Called when an Element in the Model Keyword Table is changed
    Gets the content of the Model Keyword Table, writes the Model Names in the Combo Box and saves the Mapping in the Parameter Node and the Registers
    """
    mapping = self.logic.readMappingTable(self.dialogUi.modelNametableWidget)
    combo = self.ui.ModelCheckableComboBox
    #Get current items in the Model combo Box
    currentItems = {
        combo.itemText(i): combo.model().item(i)
        for i in range(combo.count)
    }

    # remove Items, that are not part of the mapping anymore
    for name in list(currentItems.keys()):
        if name not in mapping:
            index = combo.findText(name)
            if index != -1:
                combo.removeItem(index)

    # Add items that are part of the mapping, but not of the items
    for name in sorted(mapping.keys()):
        if name not in currentItems:
            combo.addItem(name)
            item = combo.model().item(combo.count - 1)
            item.setCheckState(qt.Qt.Unchecked)
    
    #Save mapping in the parameter node and the registers
    mapping_json = json.dumps(mapping)
    self._parameterNode.SetParameter("ModelKeywordMapping", mapping_json)
    self.saveModelKeywordTable()

  def saveModelKeywordTable(self):
    """
    Saves Model Keyword Mapping in the registers
    """
    mapping = self.logic.readMappingTable(self.dialogUi.modelNametableWidget)
    settings = qt.QSettings()
    settings.setValue("SegmentationVerification/ModelKeywordMapping",
                      json.dumps(mapping))

  def onAddRow(self):
    """
    Adds a new Row to the Model Keyword table
    Called when clicking on plus in the pop up
    """
    table = self.dialogUi.modelNametableWidget
    self.onAddRowTable(table)

  def onDeleteRow(self):
    """
    Deletes a Row from the Model Keyword table
    Called when clicking on minus in the pop up
    """
    table = self.dialogUi.modelNametableWidget
    self.onDeleteRowTable(table)
    #Updates the Combo Box
    self.onModelTableItemChanged()
    #Updates the Layout when a checked Model is deleted
    self.onModelChanged()
  

  #Functions for the Segmentation Group Keyword Table
  def showSegGroupDialog(self):
    """
    Executes the Dialog/pop up to the Segmentation Group Keyword Table
    Called on clicking the + Button next to the Combo Box
    """
    self.segGroupDialog.exec_()

  def onGroupTableItemChanged(self):
    """
    Called when an Element in the segmentation Group Keyword Table is changed
    Gets the content of the Group Keyword Table, writes the Group Names in the Dropdown and saves the Mapping in the Parameter Node and the Registers
    """
    #Gets mapping and saves it in the parameter node/the registers
    mapping = self.logic.readMappingTable(self.dialogGroupUi.addGrouptable)
    mapping_json = json.dumps(mapping)
    self._parameterNode.SetParameter("GroupKeywordMapping", mapping_json)
    self.saveGroupKeywordTable()
    #Load Segmentation Groups
    self.loadSegmentationGroups()

  def saveGroupKeywordTable(self):
    """
    Saves Group Keyword Mapping in the registers
    """
    mapping = self.logic.readMappingTable(self.dialogGroupUi.addGrouptable)
    settings = qt.QSettings()
    settings.setValue("SegmentationVerification/GroupKeywordMapping",
                      json.dumps(mapping))

  def onAddRowGroup(self):
    """
    Adds a new Row to the Group Keyword table
    Called when clicking on plus in the pop up
    """
    table = self.dialogGroupUi.addGrouptable
    self.onAddRowTable(table)

  def onDeleteRowGroup(self):
    """
    Deletes a Row from the Group Keyword table
    Called when clicking on minus in the pop up
    """
    table = self.dialogGroupUi.addGrouptable
    selected_row = table.currentRow()
    selected_item_text = table.item(selected_row, 0).text() if selected_row >= 0 else None
    self.onDeleteRowTable(table)
    #updates the dropdown
    self.onGroupTableItemChanged()
    #called to change the segment group if the current group got deleted
    row_count = table.rowCount
    still_exists = False
    for r in range(row_count):
        item_text = table.item(r, 0).text()
        if item_text == selected_item_text:
            still_exists = True
            break

    if not still_exists and selected_item_text is not None:
        self.onSegmentGroupChanged()


  #Funktions for both pop ups 
  def onAddRowTable(self,table):
    """
    Adds a new Row to the table
    """
    row = table.rowCount
    table.insertRow(row)
    table.setItem(row, 0, qt.QTableWidgetItem(""))
    table.setItem(row, 1, qt.QTableWidgetItem(""))

    table.setCurrentCell(row, 0)
    table.editItem(table.item(row, 0))

  def onDeleteRowTable(self, table):
    """
    Deletes either the selected or the last row when no row is selected
    """
    selection = table.selectionModel().selectedRows()
    if selection:
        
        rows = sorted([idx.row() for idx in selection], reverse=True)
        for r in rows:
            table.removeRow(r)
    else:
        
        last = table.rowCount - 1
        if last >= 0:
            table.removeRow(last)


  #Function used in the Segmentation Comparison Collapsible Button main Window

  def onVolumeChanged(self):
    """
    Called when the Volume in the Volume Node Combo Box changes
    Load Segmentations in the checkable Dropdown for selected Volume
    Enables the Segment Selection 
    """

    if not self._parameterNode:
        return
    
    #Save the current Volume ID in the parameter Node
    currentID = self.ui.volumeNodeComboBox.currentNodeID
    self._parameterNode.SetNodeReferenceID("CurrentVolumeNode", currentID)
    #Clear the calculated Bounding Boxes for the showNeighboring Funktion
    self.logic.segmentBoundingBoxes = {}

    #Clear the Selection in the Segment Table + Set Seg Group to all
    self._parameterNode.SetParameter("VerificationTableSelection", "")
    self._parameterNode.SetParameter("SelectedGroup", "All")

    #No volume Selected -> Disable Segmentation/Model Selection
    if not currentID:
        self.ui.ModelCheckableComboBox.setEnabled(False)
        self.ui.label_models.setEnabled(False)
        self.ui.label_segmentation.setEnabled(False)
        self.ui.label_or.setEnabled(False)
        self.ui.SegmentationsCheckableComboBox.setEnabled(False)
        self.ui.openModelButton.setEnabled(False)
        return

    #Write segmentation names for the selected volume in the segmentation combo box
    segs = self.get_segmentations_for_volume()
    segNames = {seg.GetName() for seg in segs}
    self.ui.SegmentationsCheckableComboBox.clear()
    
    for name in sorted(segNames):
        self.ui.SegmentationsCheckableComboBox.addItem(name)

    #Unckeck all Models in the Model combo box
    combo = self.ui.ModelCheckableComboBox
    model = combo.model()
    #combo.blockSignals(True)
    for row in range(model.rowCount()):
        item = model.item(row)
        if item is not None:
            item.setCheckState(qt.Qt.Unchecked)
    #combo.blockSignals(False)

    #Enable checkable Combo Box for Segmentations Models + corresponding label 
    self.ui.label_segmentation.setEnabled(True)
    self.ui.SegmentationsCheckableComboBox.setEnabled(True)
    self.ui.label_or.setEnabled(True)
    self.ui.label_models.setEnabled(True)
    self.ui.ModelCheckableComboBox.setEnabled(True)
    self.ui.openModelButton.setEnabled(True)
    #Diables the Options and the Segment by Segment comparison
    for btn in (self.ui.OptionsCollapsibleButton,
                self.ui.segmentBySegmentCollapsibleButton):
        btn.setEnabled(False)
        btn.collapsed = True
     
  def onModelChanged(self):
    """
    Is called when a model is selected/disselected in the Segmentation and Segmentation Model combo boxes
    Enables/Disables Options depending on the selected models 
    Calls funktion to initilize views correspondingly 
    """
    if not self._parameterNode:
        return
    
    #Is a segmentation/model selected -> If yes enable options if no diable funktions
    hasSelection = bool(self.ui.ModelCheckableComboBox.checkedIndexes() or self.ui.SegmentationsCheckableComboBox.checkedIndexes())

    #Save the IDs of the selected Segmentations and the Selected IDs in the parameter node
    wasModified = self._parameterNode.StartModify()
    selectedIds = [ index.data() for index in self.ui.ModelCheckableComboBox.checkedIndexes() ]
    self._parameterNode.SetParameter("ModelIDs", ",".join(selectedIds))
    selectedSegmentationIds = [ index.data() for index in self.ui.SegmentationsCheckableComboBox.checkedIndexes() ]
    self._parameterNode.SetParameter("SegmentationIDs", ";".join(selectedSegmentationIds))

    #Enables/Disables ui Layout options dependig on the hasSelection value
    for w in (self.ui.threedCheckbox, self.ui.twodCheckbox,
              self.ui.label_views, self.ui.label_layout, self.ui.checkBoxVertical):
        w.setEnabled(hasSelection)
    
    #Enables/Disables threeD checkbox dependig if models are checked in the checkable combo box -> 3D View and 3D Link are activated loading a new Model
    #Checkboxes are updated through the observer that is called when the parameter node is changed
    self._parameterNode.SetParameter("Show3D", "True" if hasSelection else "False")
    self._parameterNode.SetParameter("Show2D", self._parameterNode.GetParameter("Show2D") if hasSelection else "False")
    self._parameterNode.SetParameter("VerticalLayout", self._parameterNode.GetParameter("VerticalLayout") if hasSelection else "False")
    self._parameterNode.SetParameter("OutlineRep", self._parameterNode.GetParameter("OutlineRep") if (self._parameterNode.GetParameter("Show2D") == "True") else "False")
    self._parameterNode.EndModify(wasModified)
   
    #Enables/Disables Collapsible Buttons dependig on hasSelection
    for btn in (self.ui.OptionsCollapsibleButton,
                self.ui.segmentBySegmentCollapsibleButton):
        btn.setEnabled(hasSelection)
    
    #Update Layout
    self.updateLayout()
    #Update 2D View Link
    self.onLinkThreeDViewChanged()
    self.onLinkTwoDViewChanged()

  def get_checked_models(self):
    """
    Returns selected Segmentation Model and selected Segmentation Names from checkable combo box for current/selected Volume
    """
    #Selected Model names
    model_names = [self.ui.ModelCheckableComboBox.itemText(idx.row())
            for idx in self.ui.ModelCheckableComboBox.checkedIndexes()]
    #Selected Segmentation names
    segmentation_names = [self.ui.SegmentationsCheckableComboBox.itemText(idx.row())
            for idx in self.ui.SegmentationsCheckableComboBox.checkedIndexes()]
    return model_names + segmentation_names

  def get_segmentations_for_volume(self):
    """
    Returns all Segmentation Nodes for current/selected Volume
    """
    if not self._parameterNode:
      return []

    currentID = self._parameterNode.GetNodeReferenceID("CurrentVolumeNode")
    return self._segmentationVolumeMap.get(currentID, [])

  def updateLayout(self):
    """
    Is called by onModel changed to change the view based on model selection
    Is also called, when one of the Layout checkboxes (3D View, 2D View, horizontal layout) is changed
    Apply requested view.
    """
    if not self._parameterNode:
      return 
    
    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
    #Get Layout Parameters
    view_names = self.get_checked_models()
    layout_number = len(view_names)
    #get Checkboxes
    threed_enabled = self.ui.threedCheckbox.isChecked()
    twod_enabled = self.ui.twodCheckbox.isChecked()
    vertical_layout = self.ui.checkBoxVertical.isChecked()
    #Set Parameternodes for Checkboxes
    wasModified = self._parameterNode.StartModify()
    self._parameterNode.SetParameter("VerticalLayout", str(vertical_layout))
    self._parameterNode.SetParameter("Show3D", str(threed_enabled))
    self._parameterNode.SetParameter("Show2D", str(twod_enabled))
    self._parameterNode.EndModify(wasModified)
    #Save LoadedSegmentationNodes in Parameter Node
    self.add_loaded_segmentations()

    #Get XML Code for Layout
    xml_code = self.logic.getLayoutXML(layout_number, threed_enabled, twod_enabled, vertical_layout, view_names)
    self._parameterNode.SetParameter("LayoutXML", xml_code)
    #Set Layout
    if xml_code is not None:
      layoutNode = slicer.util.getNode('*LayoutNode*')
      if layoutNode.IsLayoutDescription(layoutNode.SlicerLayoutUserView):
        layoutNode.SetLayoutDescription(layoutNode.SlicerLayoutUserView, xml_code)
      else:
        layoutNode.AddLayoutDescription(layoutNode.SlicerLayoutUserView, xml_code)
      layoutNode.SetViewArrangement(layoutNode.SlicerLayoutUserView)
      #Load Segmentations to views
      selectedVolume = slicer.util.getNode(self._parameterNode.GetNodeReferenceID("CurrentVolumeNode"))
      nodeMapping = self.get_selected_segmentation_nodes()
      status_outline = self.ui.outlineCheckBox.isChecked()
      self.logic.assignSegmentationsToViews(threed_enabled, twod_enabled, selectedVolume, nodeMapping, status_outline)
      #Enable Segmentation Options
      self.enableOptions(threed_enabled,twod_enabled)
    qt.QApplication.restoreOverrideCursor()

  def enableOptions(self, threeD, twoD):
    """
    Enables Disables the Tools based on the selected layout selection (twoD and threeD)
    """
    #Enable/Disable Collapsible Buttons (Options and Segmentation Comparison)
    for btn in (self.ui.OptionsCollapsibleButton,
                self.ui.segmentBySegmentCollapsibleButton):
        btn.setEnabled(threeD or twoD)

    self.ui.link3DViewCheckBox.setEnabled(threeD)
    self.ui.link2DViewCheckBox.setEnabled(twoD)

    self.ui.outlineCheckBox.setEnabled(twoD)

    #Set 3D Link by default, when 3D View is selected
    self.ui.link3DViewCheckBox.setChecked(threeD)
    self.onLinkThreeDViewChanged()

    if threeD or twoD:
       #Load Segmentation Groups in the dropdown
       self.loadSegmentationGroups()

    if not twoD:
        self.ui.link2DViewCheckBox.setChecked(False)
        self.ui.outlineCheckBox.setChecked(False)
        self.onLinkTwoDViewChanged()
    self.onFillingOutlineChanged()

  def onLinkThreeDViewChanged(self):
    """
    Aktivate/Deactivates the Link for the 3D Views based on the Ckeckbox
    """
    self._parameterNode.SetParameter("3DLink", "True" if self.ui.link3DViewCheckBox.isChecked() else "False")
    self.logic._set3DLink((self._parameterNode.GetParameter("3DLink") == "True"))

  def onLinkTwoDViewChanged(self):
    """
    Aktivate/Deactivates the Link for the 2D Views based on the Ckeckbox
    """
    self._parameterNode.SetParameter("2DLink", "True" if self.ui.link2DViewCheckBox.isChecked() else "False")
    self.logic._set2DLink((self._parameterNode.GetParameter("2DLink") == "True"))

  def onFillingOutlineChanged(self):
    """
    Shows only the Outline of the Segmentation in the 2D View when the checkbox is checked
    """
    self._parameterNode.SetParameter("OutlineRep", "True" if self.ui.outlineCheckBox.isChecked() else "False")
    segmentationsForVolume = self.get_segmentations_for_volume()
    self.logic._set2DFillOutline((self._parameterNode.GetParameter("OutlineRep") == "True"), segmentationsForVolume)

  def add_loaded_segmentations(self):
    """
    Stores all loaded Segmentation Nodes in the parameter node
    It saves the nodes selected by the Model combo Box in the parameter LoadedSegmentationModels and the segmentation nodes from the segmentation combo box in LoadedSegmentations
    """
    if not self._parameterNode:
        return

    segs = self.get_segmentations_for_volume()

    #Get Segmentation Nodes for the Segmentation Combo Box
    #The Combo box contains the names of the segmentation nodes so we search for the nodes with the names of the checked elements
    selectedSegNames = {
        idx.data()
        for idx in self.ui.SegmentationsCheckableComboBox.checkedIndexes()
    }
    segments_from_segcombo = [
        seg for seg in segs
        if seg.GetName() in selectedSegNames
    ]

    #Get Segmentation Nodes for each Selected Model Name
    #Segmentation Nodes are found by keywords saved in the SegModel Table -> If keyword for one Modelname is contained in the name of the segmentation node that segmentation node belongs to that model
    fullMapping = self.logic.readMappingTable(self.dialogUi.modelNametableWidget)

    selectedModels = {
        idx.data()
        for idx in self.ui.ModelCheckableComboBox.checkedIndexes()
    }
    #filtered Mapping contains the mapping for the checked models
    filteredMapping = {
        model: fullMapping[model]
        for model in selectedModels
        if model in fullMapping
    }
    #Get Seg Nodes for each model by looking if the keywords are contained in the seg node name
    segments_from_modelcombo = []
    for model, keywords in filteredMapping.items():
        
        hits = []
        for seg in segs:
            name_lower = seg.GetName().lower()
            if any(kw.lower() in name_lower for kw in keywords):
                hits.append(seg)

        # Remove duplicates per model
        # Because Models can have multible keywords; It is possible that both keywords match one segmentation node
        unique_hits = []
        for seg in hits:
            if seg not in unique_hits:
                unique_hits.append(seg)
        
        segments_from_modelcombo.extend(unique_hits)
    
    #Reset LoadedSegmentationModels and LoadedSegmentations in parameter Node
    count = self._parameterNode.GetNumberOfNodeReferences("LoadedSegmentationModels")
    for i in range(count-1, -1, -1):
        self._parameterNode.RemoveNthNodeReferenceID("LoadedSegmentationModels", i)
    
    count = self._parameterNode.GetNumberOfNodeReferences("LoadedSegmentations")
    for i in range(count-1, -1, -1):
        self._parameterNode.RemoveNthNodeReferenceID("LoadedSegmentations", i)

    #Write Seg Nodes for the Models and the Seg Nodes for the Segmentations in the corresponding parameter node
    wasModified = self._parameterNode.StartModify()

    for seg in segments_from_modelcombo:
        self._parameterNode.AddNodeReferenceID("LoadedSegmentationModels", seg.GetID())

    for seg in segments_from_segcombo:
        self._parameterNode.AddNodeReferenceID("LoadedSegmentations", seg.GetID())

    self._parameterNode.EndModify(wasModified)


  def get_selected_segmentation_nodes(self):
    """
    Returns dict Model: [segmentationNodesModel] containing selected Segmentation Nodes for each selected model and selected segmentation for current/selected Volume
    The key for the Segmentations is the Seg name 
    """
    if not self._parameterNode:
        return {}

    #Get all loaded Segmentation Nodes for selected models
    count = self._parameterNode.GetNumberOfNodeReferences("LoadedSegmentationModels")
    stored_nodes_models = [
        self._parameterNode.GetNthNodeReference("LoadedSegmentationModels", i)
        for i in range(count)
        if self._parameterNode.GetNthNodeReference("LoadedSegmentationModels", i) is not None
    ]
    #Get all loaded Segmentation Nodes for selected segmentations
    count = self._parameterNode.GetNumberOfNodeReferences("LoadedSegmentations")
    stored_nodes_segmentations = [
        self._parameterNode.GetNthNodeReference("LoadedSegmentations", i)
        for i in range(count)
        if self._parameterNode.GetNthNodeReference("LoadedSegmentations", i) is not None
    ]

    #Get Model mapping to assign seg nodes to the right model
    fullMapping = self.logic.readMappingTable(self.dialogUi.modelNametableWidget)

    checkedModels = {
        idx.data()
        for idx in self.ui.ModelCheckableComboBox.checkedIndexes()
    }
    #filteredMapping contains the Model mapping for checked models
    filteredMapping = {
        model: fullMapping[model]
        for model in checkedModels
        if model in fullMapping
    }

    mapping = {}

    #Adds the Segmentations nodes with their model names to the dict
    for model, keywords in filteredMapping.items():
        hits = []
        for seg in stored_nodes_models:
            name_lower = seg.GetName().lower()
            if any(kw.lower() in name_lower for kw in keywords):
                hits.append(seg)
        if hits:
            mapping[model] = hits
    #Adds the seg nodes from the seg combo box to the dict
    #SegName is the key for these nodes
    for seg in stored_nodes_segmentations:
        
        segName = seg.GetName()
        
        mapping[segName] = [seg]

    return mapping
  
  def loadSegmentationGroups(self):
    """
    Loads the Segmentation Groups in the dropdown based on the structures loaded
    Loads/Updates the Segmentation Table based on the group 
    """
    mapping = self.get_selected_segmentation_nodes()
    counts, info = self.logic.prepare_segmentation_data(mapping)
    structureNames = list(counts.keys())
    #Get selected Goup
    savedGroup = self._parameterNode.GetParameter("SelectedGroup")
    #Get possible Groups and Keywords
    group_defs = self.logic.readMappingTable(self.dialogGroupUi.addGrouptable)

    combo = self.ui.segmentGroupComboBox
    combo.blockSignals(True)
    combo.clear()
    #All is the default element that shows all segmentations and is always added
    combo.addItem("All")

    if not group_defs:
        #If there are no groups -> Select All by default
        combo.setCurrentIndex(0)
        self._load_structures_in_table(counts, info)
        return

    self._segmentGroupMapping = {}
    #Check with groups are present in the current segment selection
    #Assign each structure to a group -> Each structure can only occur once in a group
    groupsPresent = set()
    for struct in structureNames:
        name_lower = struct.lower()
        assigned = False
        
        for groupName, keywords in group_defs.items():
            
            if any(kw.lower() in name_lower for kw in keywords):
                self._segmentGroupMapping[struct] = groupName
                groupsPresent.add(groupName)
                assigned = True
                break
        
        if not assigned:
            #All structures that don't belong to a group are placed in the other group
            self._segmentGroupMapping[struct] = "Other"
    groupsPresent.add("Other")

    #Add present groups to the group name combo box
    for groupName in group_defs:
        if groupName in groupsPresent:
            combo.addItem(groupName)
    combo.addItem("Other")
    #Set selected element to the element before changing the group table
    idx = combo.findText(savedGroup)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)
    #If the group is not all filter out the structures that shouldn't be contained in the table 
    if savedGroup != "All":
        
        filteredCounts = {
            struct: cnt for struct, cnt in counts.items()
            if self._segmentGroupMapping.get(struct, "Other") == savedGroup
        }
        
        filteredInfo = { struct: info[struct] for struct in filteredCounts }
        counts, info = filteredCounts, filteredInfo
    #update table
    self._load_structures_in_table(counts, info)
    self._changeTableSelection()
     
  def onSegmentGroupChanged(self):
    """
    Called when another Seg Group is selected
    Displays the Segments that are part of this goup in the views
    Loads/Updates the Segmentation Table based on the group 
    """
    groupName = self.ui.segmentGroupComboBox.currentText
    if not groupName:
       return
    #Add new group name to the parameter node
    self._parameterNode.SetParameter("SelectedGroup", groupName)

    nodeMapping = self.get_selected_segmentation_nodes()
    #Clear Seg Table Selection in table + parameter node
    self._parameterNode.SetParameter("VerificationTableSelection", "")
    #Add Structures that are part of the selected goup to the views
    for segList in nodeMapping.values():
        for segNode in segList:
            displayNode = segNode.GetDisplayNode()
            if not displayNode:
                continue
            
            wasMod = displayNode.StartModify()
            ids = vtk.vtkStringArray()
            segNode.GetSegmentation().GetSegmentIDs(ids)
            for i in range(ids.GetNumberOfValues()):
                sid = ids.GetValue(i)
                segment = segNode.GetSegmentation().GetSegment(sid)
                #Try to use Snowmed mapping in DICOM Metadata instead of name, because name can be different
                tag = vtk.mutable('')
                if segment.GetTag('TerminologyEntry', tag):
                    structName = self.logic.extract_structure_name_from_terminology(tag)
                else:
                    structName = segment.GetName()
                
                segGroup = self._segmentGroupMapping.get(structName, "Other")
                
                visible = (groupName == "All" or segGroup == groupName)
                displayNode.SetSegmentVisibility(sid, visible)
                displayNode.SetSegmentOpacity(sid, 1.0)
            displayNode.EndModify(wasMod)
    #Update Table based on selected Group
    counts, info = self.logic.prepare_segmentation_data(nodeMapping)
    if groupName != "All":
        
        filteredCounts = {
            struct: cnt for struct, cnt in counts.items()
            if self._segmentGroupMapping.get(struct, "Other") == groupName
        }
        
        filteredInfo = { struct: info[struct] for struct in filteredCounts }
        counts, info = filteredCounts, filteredInfo
    self._load_structures_in_table(counts, info)

  def _load_structures_in_table(self, counts, info):
    """
    Loads Structure Name, Color, Visibilty and Opacity in the Table for each Segmented Structure contained in one of the loaded segmented structures
    Amount is the number of models that contain that structure
    """
    #Setup Table -> Rows, Header etc.
    table = self.ui.segmentationTableWidget
    table.setRowCount(len(counts))
    table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
    table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
    table.verticalHeader().setVisible(False)
    ico_v, ico_i = self._icons['visible'], self._icons['invisible']
    #Add information to rows
    for row, (struct, amt) in enumerate(counts.items()):
        #Backgroundcolor (alternating)
        bg = qt.QColor(50, 50, 50) if row % 2 == 0 else qt.QColor(30, 30, 30)
        d = info[struct]
        #Set Visibility and Backgroundcolor
        itm = qt.QTableWidgetItem() 
        itm.setIcon(ico_v if d['visibility'] else ico_i)
        itm.setBackground(bg)
        table.setItem(row, 0, itm)
        #Add Segmentation Structure color as square in the second column
        lbl = qt.QLabel()
        px = qt.QPixmap(16,16)
        c = d['color']
        px.fill(qt.QColor(*(int(v*255) for v in c)))
        lbl.setPixmap(px)
        lbl.setStyleSheet(f"background:{bg.name()}")
        lbl.setAlignment(qt.Qt.AlignCenter)
        table.setCellWidget(row, 1, lbl)
        #Write text cells in table (structurename, opacity, amount)
        for col, text in ((2, f"{d['opacity']:.2f}"), (3, struct), (4, str(amt))):
            cell = qt.QTableWidgetItem(text)
            cell.setBackground(bg)
            table.setItem(row, col, cell)
    table.viewport().update()

  def onSegmentSelectionChangedMultiple(self):
    """
    Shows selected Structure (in table selected) in all views where that structure is included.
    All other structures are hidden.
    """
    table = self.ui.segmentationTableWidget
    sel = table.selectedItems()
    if not sel:
        return
    
    selected_row = sel[0].row()
    #Save selected structure in parameter Node
    name = table.item(selected_row, 3).text()
    self._parameterNode.SetParameter("VerificationTableSelection", name)

    #Get the loaded segmentation Nodes
    loaded_mapping = self.get_selected_segmentation_nodes()  # returns dict prefix: [segNodes]
    seg_nodes = [seg for seg_list in loaded_mapping.values() for seg in seg_list]
    #For each Segnode search for the selected structure name
    #If selected structure is part of seg node select segment (show it in 2D und 3D View)
    #Otherwise just hide all Elements
    for segNode in seg_nodes:
        segs_obj = segNode.GetSegmentation()
        ids = vtk.vtkStringArray()
        segs_obj.GetSegmentIDs(ids)

        found_sid = None
        for i in range(ids.GetNumberOfValues()):
            sid = ids.GetValue(i)
            segment = segs_obj.GetSegment(sid)
            tag = vtk.mutable('')
            if segment.GetTag('TerminologyEntry', tag):
                struct = self.logic.extract_structure_name_from_terminology(tag)
            else:
                struct = segment.GetName()
            if struct == name:
                found_sid = sid
                break

        if found_sid:
            self.logic.selectSegment(self._parameterNode, found_sid, segNode)
        else:
            segNode.GetDisplayNode().SetAllSegmentsVisibility(False)

    # Set visibility icons
    ico_v = self._icons['visible']
    ico_i = self._icons['invisible']
    for r in range(table.rowCount):
        item = table.item(r, 0)
        item.setIcon(ico_v if r == selected_row else ico_i)


  def _onSegmentationTableSelectionChanged(self, index):
    """
    Selects an element of the table based on the given index (calls onSegmentSelectionChangedMultiple() on then new selected row)
    If the new index is out of bounds with the table it displays the SegmentGroup
    """
    tw = self.ui.segmentationTableWidget
    
    if index < tw.rowCount and index >= 0: 
      tw.selectRow(index)
      self.onSegmentSelectionChangedMultiple()
    else: 
      self.onSegmentGroupChanged()
       

  def onNextButtonMultiple(self):
    """
    Increases the Table Index by one
    Shows next Segmented Structure in all Views where the Segmentations contains the Structure
    """
    tw = self.ui.segmentationTableWidget
    sel = tw.selectedItems()
    if not sel: 
       return
    idx = sel[0].row() + 1
    self._onSegmentationTableSelectionChanged(idx)

  def onPreviousButtonMultiple(self):
    """
    Decreases the Table Index by one
    Shows previous Segmented Structure in all Views where the Segmentations contains the Structure
    """
    tw = self.ui.segmentationTableWidget
    sel = tw.selectedItems()
    if not sel: 
       return
    idx = sel[0].row() - 1
    self._onSegmentationTableSelectionChanged(idx)
     
#
# SegmentationVerificationLogic
#
class SegmentationVerificationLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)

    # Cached bounding boxes of all the segments
    self.segmentBoundingBoxes = {}

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("ShowNeighbors"):
      parameterNode.SetParameter("ShowNeighbors", "False")

    if not parameterNode.GetParameter("ShowNeighborsMultiple"):
      parameterNode.SetParameter("ShowNeighborsMultiple", "False")


  def assignSegmentationsToViews(self, threed_enabled, twod_enabled, selectedVolume, nodeMapping, status_outline):
    """
    Load/Assign Segmentations and Reference CT Images into Views.
    """
    layoutManager = slicer.app.layoutManager()
    #Get Mapping for: Models/Segmentations -> Segmentation files
    segmentationMapping2D = nodeMapping
    segmentationMapping = {f"View{key}": value for key, value in segmentationMapping2D.items()}
    #When 3D is enabled load 3D rendered Segmentations to 3D Views
    if threed_enabled:
        #Reset Bounding Boxes to calculate new ones for the loaded segs
        self.segmentBoundingBoxes = {}
        for i in range(layoutManager.threeDViewCount):
            threeDWidget = layoutManager.threeDWidget(i)
            threeDView = threeDWidget.threeDView()
            viewNode = threeDView.mrmlViewNode()
            viewName = viewNode.GetName()
            if viewName in segmentationMapping and segmentationMapping[viewName]:
                #Remove all Segmentation Nodes from the view
                for segmentationNode in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
                    displayNode = segmentationNode.GetDisplayNode()
                    if displayNode and viewNode.GetID() in displayNode.GetViewNodeIDs():
                        displayNode.RemoveViewNodeID(viewNode.GetID())
                        displayNode.SetVisibility3D(False)
            
                #Add Segmentation Nodes for the Model to the view
                for segmentationNode in segmentationMapping[viewName]:
                    displayNode = segmentationNode.GetDisplayNode()
                    if displayNode:
                        displayNode.SetVisibility(True)
                        displayNode.SetVisibility3D(True)
                        displayNode.AddViewNodeID(viewNode.GetID())
                    #Render View and initilize Bounding Boxes
                    segmentationNode.CreateClosedSurfaceRepresentation()
                    self.initializeSegmentBoundingBoxes(None, segmentationNode)

            threeDView.resetFocalPoint()

    #When 2D is enabled load/assign Segmentations to 2D Views
    if twod_enabled:
      for sliceViewName in ["R", "G", "Y"]:
          for modelName, segmentationNodes in segmentationMapping2D.items():
              sliceWidget = layoutManager.sliceWidget(f"{sliceViewName} {modelName}")
              compositeNode = sliceWidget.sliceLogic().GetSliceCompositeNode()
              compositeNode.SetBackgroundVolumeID(selectedVolume.GetID())
              sliceWidget.sliceController().fitSliceToBackground()
    
              viewNode = sliceWidget.mrmlSliceNode()
              viewNodeID = viewNode.GetID()
              #Remove Segmentation Nodes from View
              for segmentationNode in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
                  shownValues = [segmentation for value in list(segmentationMapping2D.values()) for segmentation in value]
                  if segmentationNode not in shownValues:
                      displayNode = segmentationNode.GetDisplayNode()
                      if displayNode:
                          displayNode.RemoveViewNodeID(viewNodeID)
                          displayNode.SetVisibility(False)
              #Assign Segmentations to View + Set Opacity to 50%
              for segmentationNode in segmentationNodes:
                  displayNode = segmentationNode.GetDisplayNode()
                  if displayNode:
                      displayNode.AddViewNodeID(viewNodeID)
                      displayNode.SetVisibility(True)
                      displayNode.SetVisibility2DFill(not status_outline)
                      displayNode.SetVisibility2DOutline(True)
                      displayNode.SetOpacity2DFill(0.5)
                      displayNode.SetOpacity2DOutline(0.5)

  def initializeSegmentBoundingBoxes(self, parameterNode, segNode=None):
    '''
    Initialize Bounding Boxes for each loaded Segmentation 
    '''
    #When Segmentation Node is not none calculate Bounding Boxes for the Segmentation Node (Segmentation Comparison)
    #Otherwise calculate Bounding Boxes for the CurrentSegmentationNode in the parameter Node (Segmentation Verification)
    if not parameterNode:
      if segNode is not None:
        segmentationNode = segNode
      else:
        raise ValueError("Invalid Input")
    else:
      segmentationNode = parameterNode.GetNodeReference("CurrentSegmentationNode")
    if not segmentationNode:
      raise ValueError("No segmentation node is selected")

    for segmentID in segmentationNode.GetSegmentation().GetSegmentIDs():
      segmentPolyData = vtk.vtkPolyData()
      segmentationNode.GetClosedSurfaceRepresentation(segmentID, segmentPolyData)

      #TODO: Apply transform if any

      segmentBounds = np.zeros(6)
      segmentPolyData.GetBounds(segmentBounds)
      segmentBoundingBox = vtk.vtkBoundingBox(segmentBounds)
      self.segmentBoundingBoxes[segmentID] = segmentBoundingBox

  def selectSegment(self, parameterNode, segmentID, segNode=None):
    '''
    Shows segment with segment ID in the corresponding view
    Shows neighboring segments semi transparent based on the bounding boxes when checkbox is clicked
    '''
    #When Segmentation Node is not none calculate Bounding Boxes for the Segmentation Node (Segmentation Comparison)
    #Otherwise calculate Bounding Boxes for the CurrentSegmentationNode in the parameter Node (Segmentation Verification)
    if segNode is not None:
      segmentationNode = segNode
      showNeighbors = parameterNode.GetParameter("ShowNeighborsMultiple") == 'True'
    else:
      segmentationNode = parameterNode.GetNodeReference("CurrentSegmentationNode")
      showNeighbors = parameterNode.GetParameter("ShowNeighbors") == 'True'
    if not segmentationNode:
      raise ValueError("No segmentation node is selected")

  
    # Center on segment also in 3D
    centerPointRas = segmentationNode.GetSegmentCenterRAS(segmentID)
    layoutManager = slicer.app.layoutManager()
    for threeDViewIndex in range(layoutManager.threeDViewCount) :
      view = layoutManager.threeDWidget(threeDViewIndex).threeDView()
      threeDViewNode = view.mrmlViewNode()
      cameraNode = slicer.modules.cameras.logic().GetViewActiveCameraNode(threeDViewNode)
      cameraNode.SetFocalPoint(centerPointRas)

    # Show only the selected segment
    displayNode = segmentationNode.GetDisplayNode()
    displayNodeWasModified = displayNode.StartModify()
    for currentSegmentID in segmentationNode.GetSegmentation().GetSegmentIDs():
      visibility = segmentID == currentSegmentID
      opacity = 1.0
      opacity2DFill = 1.0
      #Show neighbors semi transparent
      if showNeighbors and segmentID != currentSegmentID and self.getBoundingBoxCoverage(
          self.segmentBoundingBoxes[segmentID], self.segmentBoundingBoxes[currentSegmentID]) > 0.1:
        visibility = True
        opacity = 0.5
        opacity2DFill = 0.0

      displayNode.SetSegmentVisibility(currentSegmentID, visibility)
      displayNode.SetSegmentOpacity(currentSegmentID, opacity)
      displayNode.SetSegmentOpacity2DFill(currentSegmentID, opacity2DFill)

    displayNode.EndModify(displayNodeWasModified)

  def _set3DLink(self, status):
        lm = slicer.app.layoutManager()
        for i in range(lm.threeDViewCount):
            lm.threeDWidget(i).threeDView().mrmlViewNode().SetLinkedControl(status)

  def _set2DLink(self, status):
      for comp in slicer.util.getNodesByClass("vtkMRMLSliceCompositeNode"):
          comp.SetLinkedControl(status)

  def _set2DFillOutline(self, showOutline, segmentationsForVolume):
    for seg in segmentationsForVolume:
        dn = seg.GetDisplayNode()
        if not dn:
            continue
        if showOutline:
          dn.SetVisibility2DOutline(showOutline)
          dn.SetVisibility2DFill(not showOutline)
        else:
          dn.SetVisibility2DFill(not showOutline)
          dn.SetVisibility2DOutline(showOutline)
        dn.SetOpacity2DFill(0.5)
        dn.SetOpacity2DOutline(0.5)

  def setupAddTables(self, table, header):
    '''
    Creates the layout of the Add tables (ModelKeyword and GroupKeyword Table)
    '''
    table.setColumnCount(len(header))
    table.setHorizontalHeaderLabels(header)

    header = table.horizontalHeader()
    header.setSectionResizeMode(0, qt.QHeaderView.Stretch)
    header.setSectionResizeMode(1, qt.QHeaderView.Stretch)
    tableWidth = table.viewport().width or 400
    header.resizeSection(0, int(tableWidth * 0.25))
    table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
    table.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAsNeeded)
    table.setVerticalScrollBarPolicy(qt.Qt.ScrollBarAlwaysOff)

  def readMappingTable(self, table):
    '''
    Returns a dict for given table
    The Elements in the first row are the keys and the elements in the second row are used as values
    Values are split by komma e.g., moose,Moose is ["Moose", "moose"]
    '''
    mapping = {}
    for row in range(table.rowCount):
        
        keyItem = table.item(row, 0)
        if not keyItem:
            continue
        key = keyItem.text().strip()
        if not key:
            continue

        valueItem = table.item(row, 1)
        if not valueItem:
            continue
        keywords = [
            kw.strip()
            for kw in valueItem.text().split(',')
            if kw.strip()
        ]
        
        if not keywords:
            continue

        mapping[key] = keywords
    return mapping

  def extract_structure_name_from_terminology(self, terminology_string):
    """
    Extracts Structure Name from Metadata
    """
    parts = terminology_string.split('~')
    if len(parts) < 3:
        return 'Unknown'
    main = parts[2].split('^')
    name = main[2].strip() if len(main) >= 3 else parts[2].strip()
    if len(parts) >= 4:
        lat = parts[3].split('^')
        if len(lat) >= 3 and lat[2].strip() not in name:
            name += f" {lat[2].strip()}"
    return name or 'Unknown'
  
  def prepare_segmentation_data(self, mapping):
    """
    Get Segment Names, visibility and color for each loaded Structure
    """
    counts, info = {}, {}
    for segs in mapping.values():
        for seg in segs:
            dn = seg.GetDisplayNode()
            segs_obj = seg.GetSegmentation()
            ids = vtk.vtkStringArray()
            segs_obj.GetSegmentIDs(ids)
            for i in range(ids.GetNumberOfValues()):
                sid = ids.GetValue(i)
                segment = segs_obj.GetSegment(sid)
                tag = vtk.mutable('')
                struct = (self.extract_structure_name_from_terminology(tag)
                          if segment.GetTag('TerminologyEntry', tag)
                          else segment.GetName())
                vis = dn.GetSegmentVisibility(sid)
                op = dn.GetSegmentOpacity3D(sid)
                color = segment.GetColor()
                counts[struct] = counts.get(struct, 0) + 1
                if struct not in info:
                    info[struct] = {'visibility': vis, 'opacity': op, 'color': color}
    return counts, info

  def getBoundingBoxCoverage(self, firstBoundingBox, secondBoundingBox):
    """
    Returns percentage of first bounding box that is inside the second bounding box.
    :param vtkBoundingBox firstBoundingBox:
    :param vtkBoundingBox secondBoundingBox:
    :return double: Ratio of first bounding box that is inside the second bounding box (0 if no overlap, 1 for full coverage)
    """
    intersectBox = vtk.vtkBoundingBox(secondBoundingBox)
    if not intersectBox.IntersectBox(firstBoundingBox):
      return 0
    intersectBoxLengths = np.zeros(3)
    intersectBox.GetLengths(intersectBoxLengths)
    intersectBoxVolume = intersectBoxLengths.prod()
    toothBoxLengths = np.zeros(3)
    firstBoundingBox.GetLengths(toothBoxLengths)
    firstBoxVolume = toothBoxLengths.prod()

    regionBoxLengths = np.zeros(3)
    secondBoundingBox.GetLengths(regionBoxLengths)
    return intersectBoxVolume / firstBoxVolume
  
  def getLayoutXML(self, viewNumber, threedCheckbox, twodCheckbox, layout, viewNames):
    """
    Returns XML Code for the Layout.
    :param viewNumber Number of Segmentations:
    :param twodCheckbox: Enables 2D slice views (Axial, Sagittal, Coronal):
    :param threedCheckbox Enables 3D for each Segmentation:

    :return String: XML Code for the 3DSlicer Layout
    """
    layout_type_outer = "horizontal" if layout else "vertical"
    layout_type_inner = "vertical" if layout else "horizontal"

    layout_xml = f'<layout type="{layout_type_outer}" split="true">\n'

    for i in range(viewNumber):
        view_name = viewNames[i]

        layout_xml += '    <item>\n'
        layout_xml += f'        <layout type="{layout_type_inner}" split="true">\n'

        if threedCheckbox:
            layout_xml += f'''            
            <item><view class="vtkMRMLViewNode" singletontag="{view_name}">
                <property name="viewlabel" action="default">{view_name}</property>
            </view></item>
            '''

        if twodCheckbox:
            layout_xml += f'''            
            <item><view class="vtkMRMLSliceNode" singletontag="R {view_name}">
                <property name="orientation" action="default">Axial</property>
                <property name="viewlabel" action="default">R {view_name}</property>
                <property name="viewcolor" action="default">#F34A33</property>
            </view></item>
            <item><view class="vtkMRMLSliceNode" singletontag="G {view_name}">
                <property name="orientation" action="default">Sagittal</property>
                <property name="viewlabel" action="default">G {view_name}</property>
                <property name="viewcolor" action="default">#4AF333</property>
            </view></item>
            <item><view class="vtkMRMLSliceNode" singletontag="Y {view_name}">
                <property name="orientation" action="default">Coronal</property>
                <property name="viewlabel" action="default">Y {view_name}</property>
                <property name="viewcolor" action="default">#F3E833</property>
            </view></item>
            '''
        
        layout_xml += '        </layout>\n'
        layout_xml += '    </item>\n'

    layout_xml += '</layout>'
  
    return layout_xml


#
# SegmentationVerificationTest
#
class SegmentationVerificationTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear()

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_SegmentationVerification1()

  def test_SegmentationVerification1(self):
    """ Ideally you should have several levels of tests.  At the lowest level
    tests should exercise the functionality of the logic with different inputs
    (both valid and invalid).  At higher levels your tests should emulate the
    way the user would interact with your code and confirm that it still works
    the way you intended.
    One of the most important features of the tests is that it should alert other
    developers when their changes will have an impact on the behavior of your
    module.  For example, if a developer removes a feature that you depend on,
    your test should break so they know that the feature is needed.
    """

    self.delayDisplay("Starting the test")

    # Get/create input data
    self.delayDisplay('Loaded test data set')

    outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")

    # Test the module logic
    logic = SegmentationVerificationLogic()

    self.delayDisplay('Test passed')
