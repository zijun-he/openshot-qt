"""
 @file
 @brief This file loads the UI for selecting a region of a video (rectangle used for effect processing)
  @author Jonathan Thomas <jonathan@openshot.org>

 @section LICENSE

 Copyright (c) 2008-2018 OpenShot Studios, LLC
 (http://www.openshotstudios.com). This file is part of
 OpenShot Video Editor (http://www.openshot.org), an open-source project
 dedicated to delivering high quality video editing and animation solutions
 to the world.

 OpenShot Video Editor is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 OpenShot Video Editor is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with OpenShot Library.  If not, see <http://www.gnu.org/licenses/>.
 """

import os
import sys
import functools
import math

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
import openshot  # Python module for libopenshot (required video editing module installed separately)

from classes import info, ui_util, time_parts, settings, qt_types, updates
from classes.app import get_app
from classes.logger import log
from classes.metrics import *
from windows.preview_thread import PreviewParent
from windows.video_widget import VideoWidget

import json

class SelectRegion(QDialog):
    """ SelectRegion Dialog """

    # Path to ui file
    ui_path = os.path.join(info.PATH, 'windows', 'ui', 'region.ui')

    # Signals for preview thread
    previewFrameSignal = pyqtSignal(int)
    refreshFrameSignal = pyqtSignal()
    LoadFileSignal = pyqtSignal(str)
    PlaySignal = pyqtSignal(int)
    PauseSignal = pyqtSignal()
    SeekSignal = pyqtSignal(int)
    SpeedSignal = pyqtSignal(float)
    StopSignal = pyqtSignal()

    def __init__(self, file=None, clip=None):
        _ = get_app()._tr

        # Create dialog class
        QDialog.__init__(self)

        # Load UI from designer
        ui_util.load_ui(self, self.ui_path)

        # Init UI
        ui_util.init_ui(self)

        # Track metrics
        track_metric_screen("cutting-screen")

        self.start_frame = 1
        self.start_image = None
        self.end_frame = 1
        self.end_image = None
        self.current_frame = 1

        # Create region clip with Reader
        self.clip = openshot.Clip(clip.Reader())

        self.clip.Open()

        # Set region clip start and end
        self.clip.Start(clip.Start())
        self.clip.End(clip.End())
        self.clip.Id( get_app().project.generate_id() )

        print("IDS {} {}".format(clip.Id(), self.clip.Id()))

        # Keep track of file object
        self.file = file
        self.file_path = file.absolute_path()

        c_info = clip.Reader().info
        self.fps = c_info.fps.ToInt() #float(self.fps_num) / float(self.fps_den)
        self.fps_num = self.fps #int(file.data['fps']['num'])
        self.fps_den = 1 #int(file.data['fps']['den'])
        self.width = c_info.width #int(file.data['width'])
        self.height = c_info.height #int(file.data['height'])
        self.sample_rate = c_info.sample_rate #int(file.data['sample_rate'])
        self.channels = c_info.channels #int(file.data['channels'])
        self.channel_layout = c_info.channel_layout #int(file.data['channel_layout'])
        self.video_length = int(self.clip.Duration() * self.fps) + 1 #int(file.data['video_length'])

        # Apply effects to region frames
        for effect in clip.Effects():
            self.clip.AddEffect(effect)

        # Open video file with Reader
        log.info(self.clip.Reader())

        # Add Video Widget
        self.videoPreview = VideoWidget()
        self.videoPreview.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.verticalLayout.insertWidget(0, self.videoPreview)

        # Set max size of video preview (for speed)
        self.viewport_rect = self.videoPreview.centeredViewport(self.videoPreview.width(), self.videoPreview.height())

        # Create an instance of a libopenshot Timeline object
        self.r = openshot.Timeline(self.viewport_rect.width(), self.viewport_rect.height(), openshot.Fraction(self.fps_num, self.fps_den), self.sample_rate, self.channels, self.channel_layout)
        self.r.info.channel_layout = self.channel_layout
        self.r.SetMaxSize(self.viewport_rect.width(), self.viewport_rect.height())

        try:
            # Add clip for current preview file
            self.clip = openshot.Clip(self.file_path)

            # Show waveform for audio files
            if not self.clip.Reader().info.has_video and self.clip.Reader().info.has_audio:
                self.clip.Waveform(True)

            # Set has_audio property
            self.r.info.has_audio = self.clip.Reader().info.has_audio

            # Update video_length property of the Timeline object
            self.r.info.video_length = self.video_length

            self.r.AddClip(self.clip)

        except:
            log.error('Failed to load media file into region select player: %s' % self.file_path)
            return

        # Open reader
        self.r.Open()

        # Start the preview thread
        self.initialized = False
        self.transforming_clip = False
        self.preview_parent = PreviewParent()
        self.preview_parent.Init(self, self.r, self.videoPreview)
        self.preview_thread = self.preview_parent.worker

        # Set slider constraints
        self.sliderIgnoreSignal = False
        self.sliderVideo.setMinimum(1)
        self.sliderVideo.setMaximum(self.video_length)
        self.sliderVideo.setSingleStep(1)
        self.sliderVideo.setSingleStep(1)
        self.sliderVideo.setPageStep(24)

        # Determine if a start or end attribute is in this file
        start_frame = 1
        # if 'start' in self.file.data.keys():
        #     start_frame = (float(self.file.data['start']) * self.fps) + 1

        # Display start frame (and then the previous frame)
        QTimer.singleShot(500, functools.partial(self.sliderVideo.setValue, start_frame + 1))
        QTimer.singleShot(600, functools.partial(self.sliderVideo.setValue, start_frame))

        # Add buttons
        self.cancel_button = QPushButton(_('Cancel'))
        self.process_button = QPushButton(_('Select Region'))
        self.buttonBox.addButton(self.process_button, QDialogButtonBox.AcceptRole)
        self.buttonBox.addButton(self.cancel_button, QDialogButtonBox.RejectRole)

        # Connect signals
        self.actionPlay.triggered.connect(self.actionPlay_Triggered)
        self.btnPlay.clicked.connect(self.btnPlay_clicked)
        self.sliderVideo.valueChanged.connect(self.sliderVideo_valueChanged)
        self.initialized = True

        get_app().window.SelectRegionSignal.emit(clip.Id())

    def actionPlay_Triggered(self):
        # Trigger play button (This action is invoked from the preview thread, so it must exist here)
        self.btnPlay.click()

    def movePlayhead(self, frame_number):
        """Update the playhead position"""

        self.current_frame = frame_number
        # Move slider to correct frame position
        self.sliderIgnoreSignal = True
        self.sliderVideo.setValue(frame_number)
        self.sliderIgnoreSignal = False

        # Convert frame to seconds
        seconds = (frame_number-1) / self.fps

        # Convert seconds to time stamp
        time_text = time_parts.secondsToTime(seconds, self.fps_num, self.fps_den)
        timestamp = "%s:%s:%s:%s" % (time_text["hour"], time_text["min"], time_text["sec"], time_text["frame"])

        # Update label
        self.lblVideoTime.setText(timestamp)

    def btnPlay_clicked(self, force=None):
        log.info("btnPlay_clicked")

        if force == "pause":
            self.btnPlay.setChecked(False)
        elif force == "play":
            self.btnPlay.setChecked(True)

        if self.btnPlay.isChecked():
            log.info('play (icon to pause)')
            ui_util.setup_icon(self, self.btnPlay, "actionPlay", "media-playback-pause")
            self.preview_thread.Play(self.video_length)
        else:
            log.info('pause (icon to play)')
            ui_util.setup_icon(self, self.btnPlay, "actionPlay", "media-playback-start")  # to default
            self.preview_thread.Pause()

        # Send focus back to toolbar
        self.sliderVideo.setFocus()

    def sliderVideo_valueChanged(self, new_frame):
        if self.preview_thread and not self.sliderIgnoreSignal:
            log.info('sliderVideo_valueChanged')

            # Pause video
            self.btnPlay_clicked(force="pause")

            # Seek to new frame
            self.preview_thread.previewFrame(new_frame)

    def accept(self):
        """ Ok button clicked """

        self.shutdownPlayer()
        super(SelectRegion, self).accept()

    def shutdownPlayer(self):

        log.info('shutdownPlayer')

        # Stop playback
        self.preview_parent.worker.Stop()

        # Stop preview thread (and wait for it to end)
        self.preview_parent.worker.kill()
        self.preview_parent.background.exit()
        self.preview_parent.background.wait(5000)

        # Close readers
        self.clip.Close()
        # self.r.RemoveClip(self.clip)
        self.r.Close()
        # self.clip.Close()
        self.r.ClearAllCache()

    def reject(self):

        # Cancel dialog
        self.shutdownPlayer()
        super(SelectRegion, self).reject()



