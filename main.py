'''
Descripttion: 
Author: chaohui_chen1024
Date: 2024-12-27 15:45:33
LastEditors: chaohui_chen1024
LastEditTime: 2024-12-27 17:49:02
'''
import sys
import cv2
from PyQt5.QtWidgets import QApplication, QMainWindow
from base.AccessControlSystem import Ui_AccessControlSystem
from base.face_matching import FaceMatching
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer


class CameraThread(QThread):
    """子线程用于处理摄像头视频流"""
    frame_captured = pyqtSignal(QImage, object)  # 用于发送帧图像信号和检测结果

    def __init__(self):
        super().__init__()
        self.cap = None
        self.running = False

    def run(self):
        """运行摄像头线程"""
        self.cap = cv2.VideoCapture(0)  # 打开摄像头
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # 设置分辨率宽
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)  # 设置分辨率高
        self.running = True
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                # 转换为 RGB 格式
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width, channel = rgb_frame.shape
                bytes_per_line = 3 * width
                # 转换为 QImage
                q_image = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
                self.frame_captured.emit(q_image, frame)  # 发射信号，将图像发送到主线程

    def stop(self):
        """停止线程"""
        self.running = False
        if self.cap:
            self.cap.release()


class FaceDetectionThread(QThread):
    """单独的线程用于处理人脸检测"""
    detection_completed = pyqtSignal(dict)  # 用于发送人脸检测结果

    def __init__(self, face_matching):
        super().__init__()
        self.face_matching = face_matching  # 人脸匹配对象
        self.current_frame = None
        self.running = False

    def set_frame(self, frame):
        """设置当前需要检测的人脸帧"""
        self.current_frame = frame

    def run(self):
        """运行人脸检测线程"""
        self.running = True
        while self.running:
            if self.current_frame is not None:
                # 进行人脸检测
                face_encoding = self.face_matching.get_face_encoding(self.current_frame)
                if face_encoding is not None and len(face_encoding) > 0:
                    detection_result = self.face_matching.compare_faces(face_encoding)
                    result = detection_result if isinstance(detection_result, dict) else {"name": "未知", "student_ID": "未知"}
                else:
                    result = {"name": "未检测到人脸", "student_ID": "未知"}
                # 发送检测结果
                self.detection_completed.emit(result)
                self.current_frame = None  # 重置帧，避免重复处理

    def stop(self):
        """停止线程"""
        self.running = False


class MainWindow(QMainWindow, Ui_AccessControlSystem):
    def __init__(self):
        super().__init__()
        self.setupUi(self)  # 设置 UI
        self.face_matching = FaceMatching()  # 创建 FaceMatching 对象

        # 初始化摄像头线程
        self.camera_thread = CameraThread()
        self.camera_thread.frame_captured.connect(self.update_image)  # 连接信号与槽
        self.camera_thread.start()  # 启动摄像头线程

        # 初始化人脸检测线程
        self.face_detection_thread = FaceDetectionThread(self.face_matching)
        self.face_detection_thread.detection_completed.connect(self.update_information)  # 连接信号与槽
        self.face_detection_thread.start()  # 启动人脸检测线程

        # 初始化定时器，用于限制帧率
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.send_frame_for_detection)
        self.timer.start(200)  # 每隔 200 毫秒发送一帧进行检测（5 FPS）

        self.current_frame = None  # 存储当前帧
        self.is_paused = False  # 状态标志位，控制文本和图像更新
        self.pause_timer = QTimer(self)  # 用于暂停 5 秒的定时器
        self.pause_timer.setSingleShot(True)  # 设置为单次触发
        self.pause_timer.timeout.connect(self.resume_updates)  # 定时器结束后恢复更新

    def update_image(self, q_image, frame):
        """更新摄像头图像到界面"""
        if not self.is_paused:  # 只有在未暂停时更新图像
            self.current_frame = frame  # 更新最新的摄像头帧
            pixmap = QPixmap.fromImage(q_image)
            self.label_6.setPixmap(pixmap)
            self.label_6.setScaledContents(True)  # 设置标签内容自适应大小
            self.label_6.setAlignment(Qt.AlignCenter)  # 设置标签内容居中显示

    def send_frame_for_detection(self):
        """将当前帧发送到人脸检测线程"""
        if self.current_frame is not None and not self.is_paused:  # 只有在未暂停时发送帧
            self.face_detection_thread.set_frame(self.current_frame)

    def update_information(self, result):
        """更新学生信息到界面"""
        if not self.is_paused:  # 检查是否处于暂停状态
            self.textEdit.setText(result.get("name", "未知"))
            self.textEdit_2.setText(result.get("student_ID", "未知"))

            # 如果识别到学生信息（非默认值），暂停更新 5 秒
            if result.get("name", "未知") not in ["未知", "未检测到人脸"]:
                self.is_paused = True
                self.pause_timer.start(5000)  # 启动 5 秒暂停定时器

    def resume_updates(self):
        """恢复图像和文本更新"""
        self.is_paused = False

    def closeEvent(self, event):
        """关闭事件，释放资源"""
        self.camera_thread.stop()  # 停止摄像头线程
        self.camera_thread.wait()  # 等待线程结束
        self.face_detection_thread.stop()  # 停止人脸检测线程
        self.face_detection_thread.wait()  # 等待线程结束
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
