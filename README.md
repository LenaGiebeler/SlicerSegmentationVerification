# Segmentation Verification

Extension containing a 3D Slicer module (Segmentation Verification) for verifying the result of AI segmentation. The extension consists of two components:
1. **Segmentation Verification** – Allows quick and intuitive review of individual segments (masks or labels) within a single segmentation.
2. **Segmentation Comparison** – Enables the comparison of multiple segmentations or segmentation models by initializing 2D and 3D views and supporting component-wise analysis.

![image](https://raw.githubusercontent.com/cpinter/SlicerSegmentationVerification/main/SegmentationVerification.png)

For reference, the related [Slicer Project Week #41 project page](https://github.com/NA-MIC/ProjectWeek/blob/master/PW41_2024_MIT/Projects/SegmentationVerificationModuleForFinalizingMultiLabelAiSegmentations/README.md)

## How to use

1. Achieve a new AI segmentation (for example by using the [TotalSegmentator](https://github.com/lassoan/SlicerTotalSegmentator) or [MONAIAuto3DSeg](https://github.com/lassoan/SlicerMONAIAuto3DSeg) extension)
    - As an alternative you can download a sample dataset from [Imaging Data Commons](https://github.com/ImagingDataCommons/idc-index):
        - Programatically
            - `pip install --upgrade idc-index`
            - `idc download-from-selection --study-instance-uid 1.2.840.113654.2.55.119867199987299072242360817545965112631 --download-dir .`
        - You can also download it using `SlicerIDCBrowser` by pasting the UID into the study field (see [forum topic](https://discourse.slicer.org/t/sliceridcbrowser-extension-released/32279/2))
        - Or the [IDC portal on the web](https://portal.imaging.datacommons.cancer.gov/explore/)
    - Load the downloaded data as DICOM (you will need the DCMQI extension but you have it if you already installed the IDCBrowser)
2. Open the Segmentation Verification module

---

### Segmentation Verification   
https://github.com/NA-MIC/ProjectWeek/assets/1325980/77379558-be9d-4c17-a1a9-a38f78384d4b

3. Select the new segmentation if it is not already selected
4. Click on any segment to show only that one in the slice views and the 3D view as well

By going through the segments one by one and reviewing them against the anatomical image, you can evaluate the accuracy of the automatic segmentation of that specific segment.

Other options:
- If you check the "Show neighboring segments semi-transparent" checkbox, the neighboring (spatially adjacent) segments will be shown as well
- The "Previous" and "Next" buttons facilitate stepping between the segments

---

### Segmentation Comparison


3. Select the volume you want to review
4. Select one or more segmentations (The dropdown menu displays all loaded segmentations associated with the selected volume) OR select one or more segmentation models to initialize individual 3D views for each selected item
   - Segmentation models group one or more segmentations into a single model representation. This is useful when AI-based segmentation methods produce multiple output files.
   - Segmentations are automatically assigned to models based on keywords found in their names.
   - Models and associated keywords can be created, modified, or deleted by clicking the plus icon next to the segmentation dropdown.This opens a configuration table, where models
     can be edited or added. Keywords used for matching should be entered as comma-separated values.
     ![ModelKeywordTable](https://github.com/user-attachments/assets/dc146377-61a0-4fd9-a20a-5900dc90fa42)
     *Add, delete, or modify segmentation model names and associated keywords in the model configuration pop-up table*
     
5. OPTIONAL: Modify the Layout:
   - By default, 3D views are enabled when segmentations are loaded.
   - In the Instantiate Views section, you can also enable 2D views. If selected, three orthogonal 2D views (axial, sagittal, coronal) will be created for each selected segmentation
     or segmentation model, displaying the CT volume overlaid with the corresponding segmentation.
   - Each view type (2D or 3D) can be toggled on or off independently.
     ⚠️ At least one view must be enabled to visualize the data.
   - Additionally, activating the "Instantiate Vertical Layout" checkbox arranges the 2D views in a vertical layout instead of the default horizontal layout.
     
     *Vertical Layout*
     ![Vertical Layout](https://github.com/user-attachments/assets/098255bd-2593-4f72-8269-192c5aa73b95)
     *Horizontal Layout*
     ![Horizontal Layout](https://github.com/user-attachments/assets/980cc3f2-e469-483d-bfc6-ca936d3a0080)

---

Below the main controls, two collapsible sections—**Options** and **Segment by Segment Comparison**—provide additional functionality to support review and analysis workflows:

#### Options
Options allows you to adjust how the segmentations in the 2D views are displayed and how views behave:
- *Link Views:* Synchronize camera movements across all active 3D or 2D views.
- *Change Segmentation Representation to Outline:* Switches the segmentation display from filled regions to outlines.

#### Segment by Segment Comparison
The Segment by Segment Comparison panel enables detailed, structure-wise review across multiple segmentations or segmentation models.

**Key Features:**
- *Select Segmentation Group:* Choose an anatomical group (e.g., "Ribs") or select "All" to include all available segments. The table will display only the segments that
  belong to the selected group, along with the number of segmentations in which each segment is present.
  Segmentation groups can be adjusted/changed similarly to segmentation models:
  - Click the "+" button to open a configuration pop-up.
  - Each group is defined by a set of keywords. Segments whose names contain one of the keywords will be assigned to that group.
  - The group "All" is always available and contains all segments, while "Other" includes all segments that do not match any defined keyword group.
- *Segment Navigation:* Use the Previous and Next buttons to step through the segments one by one. Each selected segment is displayed simultaneously in all views, allowing for side
  by-side comparison across segmentations or models.
- *Show Neighboring Segments:* When the "Show neighboring segments semi-transparent" option is enabled, spatially adjacent structures are shown in semi-transparent mode.

![Ribs](https://github.com/user-attachments/assets/c4cd2cde-e34f-4d2f-af0c-5bd9c696937c)
*Example of the "Ribs" segmentation group: all segments with names containing keywords like "rib" are automatically grouped and displayed in the views when selected.*

![SemiTransparent](https://github.com/user-attachments/assets/382a7927-0456-4482-8a8c-bf7675e982b0)
*Structure-wise comparison of a single rib segment with neighboring segments shown semi-transparent. Neighboring structures are computed separately for each segmentation or model, based on the available segmentations. As each segmentation may contain a different set of anatomical structures, neighboring segments can vary—for example, one model might display adjacent ribs, while another includes nearby organs such as the lungs.*   
