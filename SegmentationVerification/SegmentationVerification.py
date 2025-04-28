import logging
import qt
import vtk
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import numpy as np
import random
import os


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
    self._buildSegmentationVolumeMap()
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.NodeAddedEvent, self._buildSegmentationVolumeMap)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.NodeRemovedEvent, self._buildSegmentationVolumeMap)

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    self.ui.showNeighborsCheckBox.clicked.connect(self.updateParameterNodeFromGUI)
    self.ui.showNeighboringcheckBoxMultiple.clicked.connect(self.updateParameterNodeFromGUI)

    self.ui.segmentationNodeComboBox.currentNodeChanged.connect(self.onSegmentationChanged)
    self.ui.volumeNodeComboBox.currentNodeChanged.connect(self.onVolumeChanged)
    self.ui.ModelCheckableComboBox.checkedIndexesChanged.connect(self.onModelChanged)
    self.ui.SegmentsTableView.selectionChanged.connect(self.onSegmentSelectionChanged)
    self.ui.segmentationTableWidget.selectionModel().selectionChanged.connect(self.onSegmentSelectionChangedMultiple)
    self.ui.link3DViewCheckBox.clicked.connect(self.onLinkThreeDViewChanged)
    self.ui.link2DViewCheckBox.clicked.connect(self.onLinkTwoDViewChanged)
    self.ui.outlineCheckBox.clicked.connect(self.onFillingOutlineChanged)

    self.ui.nextButton.clicked.connect(self.onNextButton)
    self.ui.previousButton.clicked.connect(self.onPreviousButton)
    self.ui.threedCheckbox.clicked.connect(self.updateLayout)
    self.ui.twodCheckbox.clicked.connect(self.updateLayout)
    self.ui.checkBoxVertical.clicked.connect(self.updateLayout)
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
    #print("Update GUI from Parameter node")
    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    self._updatingGUIFromParameterNode = True

    self.ui.segmentationNodeComboBox.setCurrentNode(self._parameterNode.GetNodeReference("CurrentSegmentationNode"))
    self.ui.volumeNodeComboBox.setCurrentNode(self._parameterNode.GetNodeReference("CurrentVolumeNode"))

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

    if not self.setUp:
      self.setUp = True
      self.setupOptions()

    self.ui.segmentationTableWidget.clearSelection()
    tableName = self._parameterNode.GetParameter("VerificationTableSelection")

    if tableName:
      table = self.ui.segmentationTableWidget
      for row in range(table.rowCount):
          item = table.item(row, 3)
          if item and item.text() == tableName:
              table.selectRow(row)
              break

    # All the GUI updates are done
    self._updatingGUIFromParameterNode = False

  def setupOptions(self):
    """
    Enables Options/Tools for comparison 
    """
    self.onVolumeChanged()

    modelIDsString = self._parameterNode.GetParameter("ModelIDs") or ""
    if modelIDsString:
        selectedIds = modelIDsString.split(",")
    else:
        selectedIds = []
    
    comboModel = self.ui.ModelCheckableComboBox.model()
    for row in range(comboModel.rowCount()):
        item = comboModel.item(row)
        itemID = item.text()
        if itemID in selectedIds:
            item.setCheckState(qt.Qt.Checked)
        else:
            item.setCheckState(qt.Qt.Unchecked)

    self.enableOptions((self._parameterNode.GetParameter("Show3D")), (self._parameterNode.GetParameter("Show2D")))
    self.configure_table()




  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """
    print("Update Parameter Node from GUI")
    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

    self._parameterNode.SetNodeReferenceID("CurrentSegmentationNode", self.ui.segmentationNodeComboBox.currentNodeID)
    self._parameterNode.SetNodeReferenceID("CurrentVolumeNode", self.ui.volumeNodeComboBox.currentNodeID)

    self._parameterNode.SetParameter("ShowNeighbors", 'True' if self.ui.showNeighborsCheckBox.checked else 'False')
    self._parameterNode.SetParameter("ShowNeighborsMultiple", 'True' if self.ui.showNeighboringcheckBoxMultiple.checked else 'False')

    selectedIds = [ index.data() for index in self.ui.ModelCheckableComboBox.checkedIndexes() ]
    self._parameterNode.SetParameter("ModelIDs", ",".join(selectedIds))

    self._parameterNode.SetParameter("Show3D", "True" if self.ui.threedCheckbox.checked else "False")
    self._parameterNode.SetParameter("Show2D", "True" if self.ui.twodCheckbox.checked else "False")
    self._parameterNode.SetParameter("VerticalLayout", "True" if self.ui.checkBoxVertical.checked else "False")
    self._parameterNode.SetParameter("3DLink", "True" if self.ui.link3DViewCheckBox.checked else "False")
    self._parameterNode.SetParameter("2DLink", "True" if self.ui.link2DViewCheckBox.checked else "False")
    self._parameterNode.SetParameter("OutlineRep", "True" if self.ui.outlineCheckBox.checked else "False")
    sel = self.ui.segmentationTableWidget.selectedItems()
    if not sel:
        return

    selected_row = sel[0].row()
    name = self.ui.segmentationTableWidget.item(selected_row, 3).text()

    self._parameterNode.SetParameter("VerificationTableSelection", name)

    self._parameterNode.EndModify(wasModified)


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




  def _buildSegmentationVolumeMap(self, caller=None, event=None):
    """
    Maps Segmentation files to one Volume
    """
    self._segmentationVolumeMap.clear()
    for seg in slicer.util.getNodesByClass('vtkMRMLSegmentationNode'):
        volRef = seg.GetNodeReference(seg.GetReferenceImageGeometryReferenceRole())
        if volRef:
            self._segmentationVolumeMap.setdefault(volRef.GetID(), []).append(seg)

  def onVolumeChanged(self):
    """
    Shows Segmentation Models for selected Volume in Dropdown 
    """
    if not self._parameterNode:
        return
    
    currentID = self.ui.volumeNodeComboBox.currentNodeID
    self._parameterNode.SetNodeReferenceID("CurrentVolumeNode", currentID)
    self.segmentBoundingBoxes = {}
    self.ui.segmentationTableWidget.clearSelection()

    #No volume Selected -> Disable Segmentationmodel Selection
    if not currentID:
        self.ui.ModelCheckableComboBox.setEnabled(False)
        self.ui.label_models.setEnabled(False)
        return

    #Uses prefixes to get Models e.g. Moose - .... is for model Moose
    segs = self.get_segmentations_for_volume()

    prefixes = {seg.GetName().split()[0] for seg in segs}

    self.ui.ModelCheckableComboBox.clear()
    #Display/Load Models in checkable Combo Box
    for name in sorted(prefixes):
        self.ui.ModelCheckableComboBox.addItem(name)
    enabled = bool(prefixes)
    #Enable checkable Combo Box for Segmentations Models + corresponding label 
    self.ui.ModelCheckableComboBox.setEnabled(enabled)
    self.ui.label_models.setEnabled(enabled)
    self.ui.segmentationTableWidget.clearSelection()



  def onModelChanged(self):
    """
    Enables/Disables Options depending on the selected models 
    Calls funktion to initilize view correspondingly 
    """
    if not self._parameterNode:
        return
    
    hasSelection = bool(self.ui.ModelCheckableComboBox.checkedIndexes())

    #Save Selected Indexes in Parameter Node
    selectedIds = [ index.data() for index in self.ui.ModelCheckableComboBox.checkedIndexes() ]
    self._parameterNode.SetParameter("ModelIDs", ",".join(selectedIds))
    #Enables/Disables ui elements dependig if models are checked in the checkable combo box
    for w in (self.ui.threedCheckbox, self.ui.twodCheckbox,
              self.ui.label_views, self.ui.label_layout, self.ui.checkBoxVertical):
        w.setEnabled(hasSelection)
    
    #Enables/Disables threeD checkbox dependig if models are checked in the checkable combo box -> 3D View and 3D Link are activated loading a new Model
    wasModified = self._parameterNode.StartModify()
    self._parameterNode.SetParameter("Show3D", "True" if hasSelection else "False")
    self._parameterNode.SetParameter("Show2D", self._parameterNode.GetParameter("Show2D") if hasSelection else "False")
    self._parameterNode.SetParameter("OutlineRep", self._parameterNode.GetParameter("OutlineRep") if (self._parameterNode.GetParameter("Show2D") == "True") else "False")
    self._parameterNode.EndModify(wasModified)
   
    #Enables/Disables ui elements dependig if models are checked in the checkable combo box
    for btn in (self.ui.OptionsCollapsibleButton,
                self.ui.SegmentationCollapsibleButton,
                self.ui.segmentationComparisonCollapsibleButton):
        btn.setEnabled(hasSelection)
    
    #Update Layout
    self.updateLayout()
    #Update 2D View Link
    self.onLinkThreeDViewChanged()
    self.onLinkTwoDViewChanged()

  def add_loaded_segmentations(self, checked_models):
    """
    Stores all segmentation nodes whose Name starts with one of the checked_models in the parameter node
    """
    if not self._parameterNode:
        return

    #Get all Segmentations Nodes for checked Models - eg. Moose checked -> All Segmentation Nodes with moose Segmentations are included in segments_to_store
    segs = self.get_segmentations_for_volume()
    segments_to_store = []
    for model in checked_models:
        segments_to_store.extend(
            [seg for seg in segs if seg.GetName().startswith(model)]
        )

    #Reset LoadedSegmentationModels in parameter Node
    count = self._parameterNode.GetNumberOfNodeReferences("LoadedSegmentationModels")
    for i in range(count-1, -1, -1):
        self._parameterNode.RemoveNthNodeReferenceID("LoadedSegmentationModels", i)
    #Reset Loaded Segmentations for checked Models to LoadedSegmentationModels in parameter Node
    wasModified = self._parameterNode.StartModify()
    for seg in segments_to_store:
        self._parameterNode.AddNodeReferenceID("LoadedSegmentationModels", seg.GetID())

    self._parameterNode.EndModify(wasModified)


  def get_selected_segmentation_nodes(self):
    """
    Returns dict Model: [segmentationNodesModel] containing selected Segmentation Nodes for each selected model for current/selected Volume
    """
    if not self._parameterNode:
        return {}

    #Get all loaded Segmentation Nodes for selected models
    count = self._parameterNode.GetNumberOfNodeReferences("LoadedSegmentationModels")
    stored_nodes = [
        self._parameterNode.GetNthNodeReference("LoadedSegmentationModels", i)
        for i in range(count)
        if self._parameterNode.GetNthNodeReference("LoadedSegmentationModels", i) is not None
    ]
    #Get all selected Models - Model has to be the prefix of the segmentaion Name
    prefixes = {seg.GetName().split()[0] for seg in stored_nodes}
    #Returns dict Model: [segmentationNodes for that Model]
    return {
        prefix: [
            seg for seg in stored_nodes
            if seg.GetName().split()[0] == prefix
        ]
        for prefix in prefixes
    }

  def get_checked_models(self):
    """
    Returns selected Segmentation Model Names from checkable combo box for current/selected Volume
    """
    return [self.ui.ModelCheckableComboBox.itemText(idx.row())
            for idx in self.ui.ModelCheckableComboBox.checkedIndexes()]

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
    self.add_loaded_segmentations(view_names)

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
    Enables Options/Tools for comparison based on the Layout
    """
    #Enable Collapsible Buttons (Options and Segmentation Comparison)
    for btn in (self.ui.OptionsCollapsibleButton,
                self.ui.SegmentationCollapsibleButton,
                self.ui.segmentationComparisonCollapsibleButton):
        btn.setEnabled(threeD or twoD)

    self.ui.link3DViewCheckBox.setEnabled(threeD)
    self.ui.link2DViewCheckBox.setEnabled(twoD)

    self.ui.outlineCheckBox.setEnabled(twoD)

    if threeD:
       self.ui.link3DViewCheckBox.setChecked(True)
       self.onLinkThreeDViewChanged()
    if threeD or twoD:
        self.configure_table()
    if not threeD:
        self.ui.link3DViewCheckBox.setChecked(False)
        self.onLinkThreeDViewChanged()
    if not twoD:
        self.ui.link2DViewCheckBox.setChecked(False)
        self.ui.outlineCheckBox.setChecked(False)
        self.onLinkTwoDViewChanged()
    self.onFillingOutlineChanged()

  def onLinkThreeDViewChanged(self):
      self._parameterNode.SetParameter("3DLink", "True" if self.ui.link3DViewCheckBox.isChecked() else "False")
      self.logic._set3DLink((self._parameterNode.GetParameter("3DLink") == "True"))

  def onLinkTwoDViewChanged(self):
      self._parameterNode.SetParameter("2DLink", "True" if self.ui.link2DViewCheckBox.isChecked() else "False")
      self.logic._set2DLink((self._parameterNode.GetParameter("2DLink") == "True"))

  def onFillingOutlineChanged(self):
      self._parameterNode.SetParameter("OutlineRep", "True" if self.ui.outlineCheckBox.isChecked() else "False")
      segmentationsForVolume = self.get_segmentations_for_volume()
      self.logic._set2DFillOutline((self._parameterNode.GetParameter("OutlineRep") == "True"), segmentationsForVolume)


  def configure_table(self):
    """
    Update/Setup Table Layout -> Load Icons etc.
    """
    table = self.ui.segmentationTableWidget
    #5 colums
    table.setColumnCount(5)
    #Icons for header
    headers = [
        ( self._icons['header_visible'], ""),
        (self._icons['header_color'], ""),
        (None, "Opacity"),  
        (None, "Name"),  
        (None, "Amount") 
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
    self.update_segmentation_table()


  def update_segmentation_table(self):
    """
    Loads Structure Name, Color, Visibilty and Opacity in the Table for each Segmented Structure contained in one of the loaded segmented structures
    Amount is the number of models that contain that structure
    """
    mapping = self.get_selected_segmentation_nodes()
    #Get Amount for each structure and information about visibility, opacity etc.
    counts, info = self.logic.prepare_segmentation_data(mapping)
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
      
  def showWholeSegmentation(self):
    """
    Shows whole Segmentation
    """
    ico = self._icons['visible']
    for seg in self.get_segmentations_for_volume():
        seg.GetDisplayNode().SetAllSegmentsVisibility(True)
    for r in range(self.ui.segmentationTableWidget.rowCount):
        self.ui.segmentationTableWidget.item(r,0).setIcon(ico)

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
    # Structure name 
    name = table.item(selected_row, 3).text()

    self._parameterNode.SetParameter("VerificationTableSelection", name)

    #Get only loaded segmentation Nodes
    loaded_mapping = self.get_selected_segmentation_nodes()  # returns dict prefix: [segNodes]
    seg_nodes = [seg for seg_list in loaded_mapping.values() for seg in seg_list]

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
    Calls onSegmentSelectionChangedMultiple on index
    """
    tw = self.ui.segmentationTableWidget
    
    if index < tw.rowCount or index >= 0: 
      tw.selectRow(index)
      self.onSegmentSelectionChangedMultiple()
    else: 
      tw.clearSelection()
      self.showWholeSegmentation()
     

  def onNextButtonMultiple(self):
    """
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
    Shows next Segmented Structure in all Views where the Segmentations contains the Structure
    """

    tw = self.ui.segmentationTableWidget
    sel = tw.selectedItems()
    if not sel: 
       return
    idx = sel[0].row() - 1
    self._onSegmentationTableSelectionChanged(idx)

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
    self.segmentBoundingBoxesAll = {}

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
    Load Segmentations and Reference CT Images into Views.
    """
    layoutManager = slicer.app.layoutManager()
    #Mapping Models -> Segmentation files
    segmentationMapping2D = nodeMapping
    segmentationMapping = {f"View{key}": value for key, value in segmentationMapping2D.items()}
    #When 3D is enabled load 3D rendered Segmentations to 3D Views
    if threed_enabled:
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
