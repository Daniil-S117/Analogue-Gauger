import cv2
from PIL import Image
import os
import numpy as np

import io


def avg_circles(circles, b):
    avg_x = 0
    avg_y = 0
    avg_r = 0
    for i in range(b):
        # необязательно — среднее значение для нескольких кругов (может произойти, если датчик находится под небольшим углом)
        avg_x = avg_x + circles[0][i][0]
        avg_y = avg_y + circles[0][i][1]
        avg_r = avg_r + circles[0][i][2]
    avg_x = int(avg_x / (b))
    avg_y = int(avg_y / (b))
    avg_r = int(avg_r / (b))
    return avg_x, avg_y, avg_r


def dist_2_pts(x1, y1, x2, y2):
    # print np.sqrt((x2-x1)^2+(y2-y1)^2)
    return np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def calibrate_gauge(img1):
    height, width = img1.shape[:2]
    gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)  # convert to gray

    # обнаружить круги
    # ограничение поиска 35-48% возможных радиусов дает достаточно хорошие результаты на разных выборках. Помните, что
    # это значения пикселей, которые соответствуют возможному диапазону поиска радиусов.
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 1, 20, np.array([]), 100, 50, int(height * 0.35),
                               int(height * 0.48))

    try:
        # average found circles, found it to be more accurate than trying to tune HoughCircles parameters to get just the right one
        a, b, c = circles.shape
        x, y, r = avg_circles(circles, b)

        # draw center and circle
        cv2.circle(img1, (x, y), r, (0, 0, 255), 3, cv2.LINE_AA)  # draw circle
        cv2.circle(img1, (x, y), 2, (0, 255, 0), 3, cv2.LINE_AA)  # draw center of circle

        separation = 10.0  # in degrees
        interval = int(360 / separation)
        p1 = np.zeros((interval, 2))  # set empty arrays
        p2 = np.zeros((interval, 2))
        p_text = np.zeros((interval, 2))
        for i in range(0, interval):
            for j in range(0, 2):
                if j % 2 == 0:
                    p1[i][j] = x + 0.9 * r * np.cos(separation * i * 3.14 / 180)  # point for lines
                else:
                    p1[i][j] = y + 0.9 * r * np.sin(separation * i * 3.14 / 180)
        text_offset_x = 10
        text_offset_y = 5
        for i in range(0, interval):
            for j in range(0, 2):
                if j % 2 == 0:
                    p2[i][j] = x + r * np.cos(separation * i * 3.14 / 180)
                    p_text[i][j] = x - text_offset_x + 1.2 * r * np.cos(
                        (separation) * (
                                i + 9) * 3.14 / 180)  # point for text labels, i+9 rotates the labels by 90 degrees
                else:
                    p2[i][j] = y + r * np.sin(separation * i * 3.14 / 180)
                    p_text[i][j] = y + text_offset_y + 1.2 * r * np.sin(
                        (separation) * (
                                i + 9) * 3.14 / 180)  # point for text labels, i+9 rotates the labels by 90 degrees

        # add the lines and labels to the image
        for i in range(0, interval):
            cv2.line(img1, (int(p1[i][0]), int(p1[i][1])), (int(p2[i][0]), int(p2[i][1])), (0, 255, 0), 2)
            cv2.putText(img1, '%s' % (int(i * separation)), (int(p_text[i][0]), int(p_text[i][1])),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.3, (0, 0, 0), 1, cv2.LINE_AA)
    except:
        x, y, r = 0, 0, 0

    return img1, x, y, r


def get_current_value(img2, min_angle, max_angle, min_value, max_value, x, y, r):
    # for testing purposes
    # img = cv2.imread('gauge-%s.%s' % (gauge_number, file_type))
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    # Set threshold and maxValue
    thresh = 175
    maxValue = 255

    # apply thresholding which helps for finding lines
    th, dst2 = cv2.threshold(gray2, thresh, maxValue, cv2.THRESH_BINARY_INV)

    # find lines
    minLineLength = 10
    maxLineGap = 0
    lines = cv2.HoughLinesP(image=dst2, rho=3, theta=np.pi / 180, threshold=100, minLineLength=minLineLength,
                            maxLineGap=0)  # rho is set to 3 to detect more lines, easier to get more then filter them out later

    # remove all lines outside a given radius
    final_line_list = []

    diff1LowerBound = 0.15  # diff1LowerBound and diff1UpperBound determine how close the line should be from the center
    diff1UpperBound = 0.25
    diff2LowerBound = 0.5  # diff2LowerBound and diff2UpperBound determine how close the other point of the line should be to the outside of the gauge
    diff2UpperBound = 1.0
    try:
        for i in range(0, len(lines)):
            for x1, y1, x2, y2 in lines[i]:
                diff1 = dist_2_pts(x, y, x1, y1)  # x, y is center of circle
                diff2 = dist_2_pts(x, y, x2, y2)  # x, y is center of circle
                # set diff1 to be the smaller (closest to the center) of the two), makes the math easier
                if (diff1 > diff2):
                    temp = diff1
                    diff1 = diff2
                    diff2 = temp
                # check if line is within an acceptable range
                if (((diff1 < diff1UpperBound * r) and (diff1 > diff1LowerBound * r) and (
                        diff2 < diff2UpperBound * r)) and (diff2 > diff2LowerBound * r)):
                    line_length = dist_2_pts(x1, y1, x2, y2)
                    # add to final list
                    final_line_list.append([x1, y1, x2, y2])

        # assumes the first line is the best one
        x1 = final_line_list[0][0]
        y1 = final_line_list[0][1]
        x2 = final_line_list[0][2]
        y2 = final_line_list[0][3]
        cv2.line(img2, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # find the farthest point from the center to be what is used to determine the angle
        dist_pt_0 = dist_2_pts(x, y, x1, y1)
        dist_pt_1 = dist_2_pts(x, y, x2, y2)
        if (dist_pt_0 > dist_pt_1):
            x_angle = x1 - x
            y_angle = y - y1
        else:
            x_angle = x2 - x
            y_angle = y - y2
        # take the arc tan of y/x to find the angle
        res = np.arctan(np.divide(float(y_angle), float(x_angle)))
        # np.rad2deg(res) #coverts to degrees

        # these were determined by trial and error
        res = np.rad2deg(res)
        if x_angle > 0 and y_angle > 0:  # in quadrant I
            final_angle = 270 - res
        if x_angle < 0 and y_angle > 0:  # in quadrant II
            final_angle = 90 - res
        if x_angle < 0 and y_angle < 0:  # in quadrant III
            final_angle = 90 - res
        if x_angle > 0 and y_angle < 0:  # in quadrant IV
            final_angle = 270 - res

        # print final_angle

        old_min = float(min_angle)
        old_max = float(max_angle)

        new_min = float(min_value)
        new_max = float(max_value)

        old_value = final_angle

        old_range = (old_max - old_min)
        new_range = (new_max - new_min)
        new_value = (((old_value - old_min) * new_range) / old_range) + new_min
    except:
        new_value = 0

    return img2, new_value


# =============================================================================


# User parameters
TO_PREDICT_PATH = "./To_Predict_Videos/"
PREDICTED_PATH = "./Predicted_Videos/"
SAVE_ANNOTATED_VIDEOS = True
MIN_SCORE = 0.4  # Minimum object detection score
# for testing purposes: hardcode and comment out raw_inputs above
min_angle = 45
max_angle = 320
min_value = 0
max_value = 14
units = "Кл."

# Loops through each video found in TO_PREDICT_PATH folder
for video_name in os.listdir(TO_PREDICT_PATH):
    video_path = os.path.join(TO_PREDICT_PATH, video_name)

    video_capture = cv2.VideoCapture(video_path)

    # Video frame count and fps needed for VideoWriter settings
    frame_count = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = round(video_capture.get(cv2.CAP_PROP_FPS))

    # If successful and image of frame
    success, image_b4_color = video_capture.read()

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_out = cv2.VideoWriter(PREDICTED_PATH + video_name, fourcc, video_fps,
                                (int(image_b4_color.shape[1]),
                                 int(image_b4_color.shape[0])))

    nFrame = 0
    # If still seeing video, loops through each frame in video
    while success:
        success, image_b4_color = video_capture.read()
        if not success:
            break
        nFrame += 1
        # -----------------------------------------------------------------------------
        # Загружает изображение
        image = cv2.cvtColor(image_b4_color, cv2.COLOR_BGR2RGB)


        # Код для обработки кадров видео и создания нового видео из этих кадров
        # Используй переменную image в функциях на выход должна поступить переменная img2
        # Алгоритм работает долго, может потребоваться несколько минут
        '''if nFrame % 10 == 1:
            img1, x, y, r = calibrate_gauge(image)
        img2, val = get_current_value(image, min_angle, max_angle, min_value, max_value, x, y, r)'''
        # -----------------------------------------------------------------------------


        print('Frame ', nFrame)
        # Сохраняет кадры видео
        video_out.write(img2)

    video_out.release()

print("Done!")
# =============================================================================