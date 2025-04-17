import logging
import qt
import vtk
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import numpy as np
import random
import os

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

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    self.ui.showNeighborsCheckBox.clicked.connect(self.updateParameterNodeFromGUI)

    self.ui.segmentationNodeComboBox.currentNodeChanged.connect(self.onSegmentationChanged)
    self.ui.volumeNodeComboBox.currentNodeChanged.connect(self.onVolumeChanged)
    self.ui.ModelCheckableComboBox.checkedIndexesChanged.connect(self.onModelChanged)
    self.ui.SegmentsTableView.selectionChanged.connect(self.onSegmentSelectionChanged)
    self.ui.segmentationTableWidget.selectionModel().selectionChanged.connect(self.onSegmentSelectionChanged_all_models)
    self.ui.link3DViewCheckBox.clicked.connect(self.onLinkThreeDViewChanged)
    self.ui.link2DViewCheckBox.clicked.connect(self.onLinkTwoDViewChanged)
    self.ui.outlineCheckBox.clicked.connect(self.onFillingOutlineChanged)

    self.ui.nextButton.clicked.connect(self.onNextButton)
    self.ui.previousButton.clicked.connect(self.onPreviousButton)
    self.ui.threedCheckbox.clicked.connect(self.onViewButton)
    self.ui.twodCheckbox.clicked.connect(self.onViewButton)
    self.ui.checkBoxVertical.clicked.connect(self.onViewButton)
    self.ui.nextButton_comparison.clicked.connect(self.onNextButton_comparison)
    self.ui.previousButton_comparison.clicked.connect(self.onPreviousButton_comparison)

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

    self.ui.segmentationNodeComboBox.setCurrentNode(self._parameterNode.GetNodeReference("CurrentSegmentationNode"))
    self.ui.volumeNodeComboBox.setCurrentNode(self._parameterNode.GetNodeReference("CurrentVolumeNode"))

    showNeighbors = self._parameterNode.GetParameter("ShowNeighbors")
    self.ui.showNeighborsCheckBox.checked = True if showNeighbors == 'True' else False

    # All the GUI updates are done
    self._updatingGUIFromParameterNode = False

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

  def onVolumeChanged(self):
    
    if not self._parameterNode:
        return

    currentNodeID = self.ui.volumeNodeComboBox.currentNodeID

    wasModified = self._parameterNode.StartModify()
    self._parameterNode.SetNodeReferenceID("CurrentVolumeNode", currentNodeID)
    self._parameterNode.EndModify(wasModified)

    if not currentNodeID:
       self.ui.ModelCheckableComboBox.setEnabled(False)
       self.ui.label_models.setEnabled(False)
       return

    self.ui.ModelCheckableComboBox.setEnabled(True)
    self.ui.label_models.setEnabled(True)
    selectedVolume = slicer.util.getNode(currentNodeID)

    self.ui.ModelCheckableComboBox.clear()
    unique_segment_names = set()
    segmentationNodes = slicer.util.getNodesByClass('vtkMRMLSegmentationNode')
    for segmentationNode in segmentationNodes:
        refCT = segmentationNode.GetNodeReference(
            segmentationNode.GetReferenceImageGeometryReferenceRole()
        )
        if refCT and refCT.GetID() == selectedVolume.GetID():
            nodeName = segmentationNode.GetName()
            unique_segment_names.add(nodeName.split(" ")[0])

    for name in sorted(unique_segment_names): 
        self.ui.ModelCheckableComboBox.addItem(name)



  def onModelChanged(self):
     checked_count = len(self.ui.ModelCheckableComboBox.checkedIndexes())
     if checked_count > 0:
        self.ui.threedCheckbox.setEnabled(True)
        self.ui.twodCheckbox.setEnabled(True)
        self.ui.label_views.setEnabled(True)
        self.ui.label_layout.setEnabled(True)
        self.ui.checkBoxVertical.setEnabled(True)
        self.ui.threedCheckbox.setChecked(True)
        self.onViewButton()
     else:
        self.ui.twodCheckbox.setDisabled(True)
        self.ui.threedCheckbox.setDisabled(True)
        self.ui.label_views.setDisabled(True)
        self.ui.label_layout.setDisabled(True)
        self.ui.checkBoxVertical.setDisabled(True)
        self.ui.twodCheckbox.setChecked(False)
        self.ui.threedCheckbox.setChecked(False)
        self.ui.checkBoxVertical.setChecked(False)
        self.ui.outlineCheckBox.setChecked(False)
        self.onViewButton()
        self.onLinkThreeDViewChanged()
        self.onLinkTwoDViewChanged()
        self.ui.OptionsCollapsibleButton.setEnabled(False)
        self.ui.SegmentationCollapsibleButton.setEnabled(False)
        self.ui.segmentationComparisonCollapsibleButton.setEnabled(False)

  def get_checked_models(self):
    view_names = []
    for index in self.ui.ModelCheckableComboBox.checkedIndexes():
        view_names.append(self.ui.ModelCheckableComboBox.itemText(index.row()))
    return view_names
  
  def get_selected_segmentation_nodes(self, checked_models):
    segmentationMapping = {}
    selectedVolume = slicer.util.getNode(self.ui.volumeNodeComboBox.currentNodeID)
    allSegmentations = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")

    for checked_model in checked_models:
        matchingSegmentations = [
            seg for seg in allSegmentations if seg.GetName().startswith(checked_model) and seg.GetNodeReference(seg.GetReferenceImageGeometryReferenceRole()).GetID() == selectedVolume.GetID()
        ]
        
        if checked_model not in segmentationMapping:
            segmentationMapping[checked_model] = []

        segmentationMapping[checked_model].extend(matchingSegmentations)

    return segmentationMapping
  
  def get_segmentations_for_volume(self):
    selectedVolume = slicer.util.getNode(self.ui.volumeNodeComboBox.currentNodeID)
    if not selectedVolume:
        return []
    allSegmentations = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
    matchingSegmentations = [
            seg for seg in allSegmentations if seg.GetNodeReference(seg.GetReferenceImageGeometryReferenceRole()).GetID() == selectedVolume.GetID()
        ]

    return matchingSegmentations


  def onViewButton(self):
    """
    Apply requested view.
    """
    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
    view_names = self.get_checked_models()
    layout_number = len(view_names)
    threed_enabled = self.ui.threedCheckbox.isChecked()
    twod_enabled = self.ui.twodCheckbox.isChecked()
    vertical_layout = self.ui.checkBoxVertical.isChecked()
    xml_code = self.logic.getLayoutXML(layout_number, threed_enabled, twod_enabled, vertical_layout, view_names)
    if xml_code is not None:
      layoutNode = slicer.util.getNode('*LayoutNode*')
      if layoutNode.IsLayoutDescription(layoutNode.SlicerLayoutUserView):
        layoutNode.SetLayoutDescription(layoutNode.SlicerLayoutUserView, xml_code)
      else:
        layoutNode.AddLayoutDescription(layoutNode.SlicerLayoutUserView, xml_code)
      layoutNode.SetViewArrangement(layoutNode.SlicerLayoutUserView)
      self.assignSegmentationsToViews(view_names, threed_enabled, twod_enabled)
      self.enableOptions(threed_enabled,twod_enabled)
    qt.QApplication.restoreOverrideCursor()

  def assignSegmentationsToViews(self, view_names, threed_enabled, twod_enabled):
    """
    Load Segmentations and Reference CT Images into Views.
    """
    layoutManager = slicer.app.layoutManager()
    segmentationMapping2D = self.get_selected_segmentation_nodes(view_names)
    selectedVolume = slicer.util.getNode(self.ui.volumeNodeComboBox.currentNodeID)
    segmentationMapping = {f"View{key}": value for key, value in segmentationMapping2D.items()}

    if threed_enabled:
        for i in range(layoutManager.threeDViewCount):
            threeDWidget = layoutManager.threeDWidget(i)
            threeDView = threeDWidget.threeDView()
            viewNode = threeDView.mrmlViewNode()
            viewName = viewNode.GetName()
            if viewName in segmentationMapping and segmentationMapping[viewName]:
                for segmentationNode in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
                    displayNode = segmentationNode.GetDisplayNode()
                    if displayNode and viewNode.GetID() in displayNode.GetViewNodeIDs():
                        displayNode.RemoveViewNodeID(viewNode.GetID())
                        displayNode.SetVisibility3D(False)

                for segmentationNode in segmentationMapping[viewName]:
                    displayNode = segmentationNode.GetDisplayNode()
                    if displayNode:
                        displayNode.SetVisibility(True)
                        displayNode.SetVisibility3D(True)
                        displayNode.AddViewNodeID(viewNode.GetID())
                    segmentationNode.CreateClosedSurfaceRepresentation()

            threeDView.resetFocalPoint()

    if twod_enabled:
      for sliceViewName in ["R", "G", "Y"]:
          for modelName, segmentationNodes in segmentationMapping2D.items():
              sliceWidget = layoutManager.sliceWidget(f"{sliceViewName} {modelName}")
              compositeNode = sliceWidget.sliceLogic().GetSliceCompositeNode()
              compositeNode.SetBackgroundVolumeID(selectedVolume.GetID())
              sliceWidget.sliceController().fitSliceToBackground()
    
              viewNode = sliceWidget.mrmlSliceNode()
              viewNodeID = viewNode.GetID()

              for segmentationNode in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
                  shownValues = [segmentation for value in list(segmentationMapping2D.values()) for segmentation in value]
                  if segmentationNode not in shownValues:
                      displayNode = segmentationNode.GetDisplayNode()
                      if displayNode:
                          displayNode.RemoveViewNodeID(viewNodeID)
                          displayNode.SetVisibility(False)

              for segmentationNode in segmentationNodes:
                  displayNode = segmentationNode.GetDisplayNode()
                  if displayNode:
                      displayNode.AddViewNodeID(viewNodeID)
                      status_outline = self.ui.outlineCheckBox.isChecked()
                      displayNode.SetVisibility(True)
                      displayNode.SetVisibility2DFill(not status_outline)
                      displayNode.SetVisibility2DOutline(True)
                      displayNode.SetOpacity2DFill(0.5)
                      displayNode.SetOpacity2DOutline(0.5)

  def enableOptions(self, threeD, twoD):
     self.setSegmentationNodeComboBox()
     if threeD and not twoD:
        self.ui.link3DViewCheckBox.setEnabled(True)
        self.ui.link2DViewCheckBox.setDisabled(True)
        self.ui.link2DViewCheckBox.setChecked(False)
        self.ui.link3DViewCheckBox.setChecked(True)
        self.ui.OptionsCollapsibleButton.setEnabled(True)
        self.ui.SegmentationCollapsibleButton.setEnabled(True)
        self.ui.segmentationComparisonCollapsibleButton.setEnabled(True)
        self.ui.label_segRepresentation.setDisabled(True)
        self.ui.outlineCheckBox.setDisabled(True)
        self.ui.outlineCheckBox.setChecked(False)
        self.configure_table()
        self.onFillingOutlineChanged()
        self.onLinkTwoDViewChanged()
        self.onLinkThreeDViewChanged()
     elif twoD and not threeD:
        self.ui.link3DViewCheckBox.setDisabled(True)
        self.ui.link2DViewCheckBox.setEnabled(True)
        self.ui.link3DViewCheckBox.setChecked(False)
        self.ui.OptionsCollapsibleButton.setEnabled(True)
        self.ui.SegmentationCollapsibleButton.setEnabled(True)
        self.ui.segmentationComparisonCollapsibleButton.setEnabled(True)
        self.configure_table()
        self.ui.label_segRepresentation.setEnabled(True)
        self.ui.outlineCheckBox.setEnabled(True)
     elif twoD and threeD:
        self.ui.link3DViewCheckBox.setEnabled(True)
        self.ui.link2DViewCheckBox.setEnabled(True)
        self.ui.link3DViewCheckBox.setChecked(True)
        self.ui.OptionsCollapsibleButton.setEnabled(True)
        self.ui.SegmentationCollapsibleButton.setEnabled(True)
        self.ui.segmentationComparisonCollapsibleButton.setEnabled(True)
        self.configure_table()
        self.ui.label_segRepresentation.setEnabled(True)
        self.ui.outlineCheckBox.setEnabled(True)
        self.onLinkThreeDViewChanged()
     else:
       self.ui.OptionsCollapsibleButton.setEnabled(False)
       self.ui.SegmentationCollapsibleButton.setEnabled(False)
       self.ui.segmentationComparisonCollapsibleButton.setEnabled(False)
       self.ui.link2DViewCheckBox.setChecked(False)
       self.ui.link3DViewCheckBox.setChecked(False)
       self.ui.outlineCheckBox.setEnabled(False)
       self.onFillingOutlineChanged()
       self.onLinkTwoDViewChanged()
       self.onLinkThreeDViewChanged()
        
  def onLinkThreeDViewChanged(self):
    layoutManager = slicer.app.layoutManager()
    status = self.ui.link3DViewCheckBox.isChecked()
    for i in range(layoutManager.threeDViewCount):
      threeDWidget = layoutManager.threeDWidget(i)
      viewNode = threeDWidget.threeDView().mrmlViewNode()  
      if status:
        viewNode.SetLinkedControl(True)
      else:
        viewNode.SetLinkedControl(False)

  def onLinkTwoDViewChanged(self):
    status = self.ui.link2DViewCheckBox.isChecked()
    sliceCompositeNodes = slicer.util.getNodesByClass("vtkMRMLSliceCompositeNode")

    defaultSliceCompositeNode = slicer.mrmlScene.GetDefaultNodeByClass("vtkMRMLSliceCompositeNode")
    if not defaultSliceCompositeNode:
        defaultSliceCompositeNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSliceCompositeNode")
        defaultSliceCompositeNode.UnRegister(None)
        slicer.mrmlScene.AddDefaultNode(defaultSliceCompositeNode)
    sliceCompositeNodes.append(defaultSliceCompositeNode)
    for sliceCompositeNode in sliceCompositeNodes:
        sliceCompositeNode.SetLinkedControl(status)

  def onFillingOutlineChanged(self):
     status_outline = self.ui.outlineCheckBox.isChecked()
     for segmentationNode in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
        displayNode = segmentationNode.GetDisplayNode()
        if displayNode:
          if status_outline:
            displayNode.SetVisibility2DFill(False)
            displayNode.SetVisibility2DOutline(status_outline)
            displayNode.SetOpacity2DOutline(0.5)
          else:
            displayNode.SetVisibility2DFill(True)
            displayNode.SetOpacity2DFill(0.5)
            displayNode.SetVisibility2DOutline(True)
            displayNode.SetOpacity2DOutline(0.5)


  def configure_table(self):
    
    self.ui.segmentationTableWidget.setColumnCount(5)

    base_path = os.path.dirname(os.path.abspath(__file__))

    header_labels = [
        (qt.QIcon(os.path.join(base_path, "Resources", "Icons", "SlicerVisibleInvisible.png")), ""),
        (qt.QIcon(os.path.join(base_path, "Resources", "Icons", "SlicerAddTransform.png")), ""),
        (None, "Opacity"),  
        (None, "Name"),  
        (None, "Amount") 
    ]

    for col, (icon, text) in enumerate(header_labels):
        if icon:  
            header_item = qt.QTableWidgetItem(icon, text)
        else:
            header_item = qt.QTableWidgetItem(text)
        
        self.ui.segmentationTableWidget.setHorizontalHeaderItem(col, header_item)

    header = self.ui.segmentationTableWidget.horizontalHeader()

    header.setSectionResizeMode(0, qt.QHeaderView.ResizeToContents)  
    header.setSectionResizeMode(1, qt.QHeaderView.ResizeToContents)  
    header.setSectionResizeMode(2, qt.QHeaderView.ResizeToContents) 

    header.setSectionResizeMode(4, qt.QHeaderView.ResizeToContents)

    header.setSectionResizeMode(3, qt.QHeaderView.Stretch)

    self.ui.segmentationTableWidget.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAlwaysOff)

    self.ui.segmentationTableWidget.horizontalHeader().setVisible(True)
    self.load_segmentation_data()


  def extract_structure_name_from_terminology(self, terminology_string):
    try:
        parts = terminology_string.split("~")
        if len(parts) >= 3:
            subparts = parts[2].split("^")
            if len(subparts) >= 3:
                structure_name = subparts[2].strip()
            else:
                structure_name = parts[2].strip()
        else:
            return "Unknown"

        if len(parts) >= 4:
            subparts2 = parts[3].split("^")
            if len(subparts2) >= 3:
                laterality = subparts2[2].strip()
                if laterality and laterality not in structure_name:
                    structure_name += " " + laterality
        return structure_name
    except Exception as e:
        print(f"Fehler bei extract_structure_name_from_terminology: {e}")
    return "Unknown"


  def load_segmentation_data(self):

    view_names = self.get_checked_models()
    segmentationMapping2D = segmentationMapping2D = self.get_selected_segmentation_nodes(view_names)

    structure_count = {}
    structure_data = {} 

    for segmentations in segmentationMapping2D.values():
        for segmentation in segmentations:
            segmentation_node = slicer.mrmlScene.GetNodeByID(segmentation.GetID())
            segment_ids = vtk.vtkStringArray()
            segmentation_node.GetSegmentation().GetSegmentIDs(segment_ids)

            for i in range(segment_ids.GetNumberOfValues()):
                segment_id = segment_ids.GetValue(i)
                segment = segmentation_node.GetSegmentation().GetSegment(segment_id)
                value_ref = vtk.mutable("")
                if segment.GetTag("TerminologyEntry", value_ref):
                    terminology_string = value_ref
                    structure_name = self.extract_structure_name_from_terminology(terminology_string)
                else:
                    structure_name = segment.GetName()


                visibility = segmentation_node.GetDisplayNode().GetSegmentVisibility(segment_id)
                opacity = segmentation_node.GetDisplayNode().GetSegmentOpacity3D(segment_id)
                r, g, b = segment.GetColor()

                if structure_name in structure_count:
                    structure_count[structure_name] += 1
                else:
                    structure_count[structure_name] = 1
                    structure_data[structure_name] = {
                        "visibility": visibility,
                        "opacity": opacity,
                        "color": (r, g, b)
                    }

    self.update_segmentation_table(structure_count, structure_data)


  def update_segmentation_table(self, structure_count, structure_data):

      self.ui.segmentationTableWidget.setRowCount(len(structure_count))  
      self.ui.segmentationTableWidget.setSelectionBehavior(qt.QAbstractItemView.SelectRows)  
      self.ui.segmentationTableWidget.setSelectionMode(qt.QAbstractItemView.SingleSelection)
      self.ui.segmentationTableWidget.verticalHeader().setVisible(False)

      base_path = os.path.dirname(os.path.abspath(__file__))  

      for row, (structure_name, amount) in enumerate(structure_count.items()):
          data = structure_data[structure_name]

          background_color = qt.QColor(50, 50, 50) if row % 2 == 0 else qt.QColor(30, 30, 30)

          visibility_icon_path = os.path.join(base_path, "Resources", "Icons", "SlicerVisible.png") \
              if data["visibility"] else os.path.join(base_path, "Resources", "Icons", "SlicerInvisible.png")

          icon_item = qt.QTableWidgetItem()
          icon_item.setIcon(qt.QIcon(visibility_icon_path))
          icon_item.setBackground(background_color)
          self.ui.segmentationTableWidget.setItem(row, 0, icon_item)

          color_label = qt.QLabel()
          pixmap = qt.QPixmap(16, 16)
          pixmap.fill(qt.QColor(int(data["color"][0] * 255), int(data["color"][1] * 255), int(data["color"][2] * 255)))
          color_label.setPixmap(pixmap)
          color_label.setAlignment(qt.Qt.AlignCenter)

          color_label.setStyleSheet(f"background-color: rgb({background_color.red()}, {background_color.green()}, {background_color.blue()});")

          self.ui.segmentationTableWidget.setCellWidget(row, 1, color_label)

          opacity_item = qt.QTableWidgetItem(f"{data['opacity']:.2f}")
          opacity_item.setBackground(background_color)
          self.ui.segmentationTableWidget.setItem(row, 2, opacity_item)

          name_item = qt.QTableWidgetItem(structure_name)
          name_item.setBackground(background_color)
          self.ui.segmentationTableWidget.setItem(row, 3, name_item)

          amount_item = qt.QTableWidgetItem(str(amount))
          amount_item.setBackground(background_color)
          self.ui.segmentationTableWidget.setItem(row, 4, amount_item)

      self.ui.segmentationTableWidget.viewport().update()

  def setSegmentationNodeComboBox(self):
      '''
      view_names = []
      for index in self.ui.ModelCheckableComboBox.checkedIndexes():
          view_names.append(self.ui.ModelCheckableComboBox.itemText(index.row()))

      filtered_segmentations = []

      for segmentationNode in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
          node_name = segmentationNode.GetName()
          if any(node_name.startswith(view_name) for view_name in view_names):
              filtered_segmentations.append(segmentationNode)

      self.ui.segmentationNodeComboBox.setMRMLScene(None)
      self.ui.segmentationNodeComboBox.setMRMLScene(slicer.mrmlScene)
      for segNode in filtered_segmentations:
          self.ui.segmentationNodeComboBox.addNode(segNode)
    '''
      
  def showWholeSegmentation(self):
    allSegmentations = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")

    for segmentation_node in allSegmentations:
        displayNode = segmentation_node.GetDisplayNode()
        displayNode.SetAllSegmentsVisibility(True)

    base_path = os.path.dirname(os.path.abspath(__file__))  

    visible_icon_path = os.path.join(base_path, "Resources", "Icons", "SlicerVisible.png")

    row_count = self.ui.segmentationTableWidget.rowCount
    for row in range(row_count):
        icon_item = self.ui.segmentationTableWidget.item(row, 0)
        icon_item.setIcon(qt.QIcon(visible_icon_path))

        

  def onSegmentSelectionChanged_all_models(self):

    selected_items = self.ui.segmentationTableWidget.selectedItems()
    if not selected_items:
        return 

    selected_row = selected_items[0].row()
    selectedSegmentName = self.ui.segmentationTableWidget.item(selected_row, 3).text()

    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)

    allSegmentations = self.get_segmentations_for_volume()
    for segmentation_node in allSegmentations:
        displayNode = segmentation_node.GetDisplayNode()
        displayNode.SetAllSegmentsVisibility(False)
        segment_ids = vtk.vtkStringArray()
        segmentation_node.GetSegmentation().GetSegmentIDs(segment_ids)

        for i in range(segment_ids.GetNumberOfValues()):
            segment_id = segment_ids.GetValue(i)
            segment = segmentation_node.GetSegmentation().GetSegment(segment_id)

            value_ref = vtk.mutable("")
            if segment.GetTag("TerminologyEntry", value_ref):
                terminology_string = value_ref
                structure_name = self.extract_structure_name_from_terminology(terminology_string)
            else:
                structure_name = segment.GetName()

            if structure_name == selectedSegmentName:
                new_visibility = not displayNode.GetSegmentVisibility(segment_id)
                displayNode.SetSegmentVisibility(segment_id, new_visibility)
                displayNode.SetSegmentVisibility(segment_id, True)

    qt.QApplication.restoreOverrideCursor()
    base_path = os.path.dirname(os.path.abspath(__file__))  

    visible_icon_path = os.path.join(base_path, "Resources", "Icons", "SlicerVisible.png")
    invisible_icon_path = os.path.join(base_path, "Resources", "Icons", "SlicerInvisible.png")

    row_count = self.ui.segmentationTableWidget.rowCount
    icon_column = 0

    for row in range(row_count):
        icon_item = self.ui.segmentationTableWidget.item(row, icon_column)
        if not icon_item:
            icon_item = qt.QTableWidgetItem()
            self.ui.segmentationTableWidget.setItem(row, icon_column, icon_item)

        if row == selected_row:
            icon_item.setIcon(qt.QIcon(visible_icon_path))
        else:
            icon_item.setIcon(qt.QIcon(invisible_icon_path))


  def onNextButton_comparison(self):

    selected_items = self.ui.segmentationTableWidget.selectedItems()
    if not selected_items:
        return

    selected_row = selected_items[0].row()
    next_row = selected_row + 1

    if next_row < self.ui.segmentationTableWidget.rowCount: 
        self.ui.segmentationTableWidget.selectRow(next_row)
        next_items = [self.ui.segmentationTableWidget.item(next_row, col) for col in range(self.ui.segmentationTableWidget.columnCount)]
        
        if next_items and next_items[0]:  
            self.onSegmentSelectionChanged_all_models()
    else:
       self.ui.segmentationTableWidget.clearSelection()
       self.showWholeSegmentation()

  def onPreviousButton_comparison(self):
    selected_items = self.ui.segmentationTableWidget.selectedItems()
    if not selected_items:
        return

    selected_row = selected_items[0].row()
    next_row = selected_row - 1

    if next_row >= 0: 
        self.ui.segmentationTableWidget.selectRow(next_row)
        next_items = [self.ui.segmentationTableWidget.item(next_row, col) for col in range(self.ui.segmentationTableWidget.columnCount)]
        
        if next_items and next_items[0]:  
            self.onSegmentSelectionChanged_all_models()
    else:
       self.ui.segmentationTableWidget.clearSelection()
       self.showWholeSegmentation()

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

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("ShowNeighbors"):
      parameterNode.SetParameter("ShowNeighbors", "False")

  def initializeSegmentBoundingBoxes(self, parameterNode):
    if not parameterNode:
      raise ValueError("Invalid parameter node")
    segmentationNode = parameterNode.GetNodeReference("CurrentSegmentationNode")
    if not segmentationNode:
      raise ValueError("No segmentation node is selected")

    self.segmentBoundingBoxes = {}

    for segmentID in segmentationNode.GetSegmentation().GetSegmentIDs():
      segmentPolyData = vtk.vtkPolyData()
      segmentationNode.GetClosedSurfaceRepresentation(segmentID, segmentPolyData)

      #TODO: Apply transform if any

      segmentBounds = np.zeros(6)
      segmentPolyData.GetBounds(segmentBounds)
      segmentBoundingBox = vtk.vtkBoundingBox(segmentBounds)
      self.segmentBoundingBoxes[segmentID] = segmentBoundingBox

  def selectSegment(self, parameterNode, segmentID):
    if not parameterNode:
      raise ValueError("Invalid parameter node")
    segmentationNode = parameterNode.GetNodeReference("CurrentSegmentationNode")
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

    showNeighbors = parameterNode.GetParameter("ShowNeighbors") == 'True'

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
