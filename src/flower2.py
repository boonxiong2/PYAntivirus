# imports
import turtle
import turtle as t
import easygui as gui

# define value
last_pos = None


# defines
def flower(colour: str, size: int, pen, pos: list):
    """
    绘制一朵花
    size: 控制花朵大小
    pos: 花朵中心位置
    """
    pen.speed("fastest")
    try:
        # 移动到花朵中心
        pen.up()
        pen.goto(pos[0], pos[1])
        pen.down()

        # 设置颜色
        pen.color(colour)
        pen.fillcolor(colour)

        # 画花心
        pen.begin_fill()
        pen.circle(size / 4)  # 花心比花瓣小
        pen.end_fill()

        # 画花瓣
        pen.pensize(size / 20)  # 根据花朵大小调整线条粗细

        # 画5个花瓣
        for _ in range(5):
            pen.up()
            pen.goto(pos[0], pos[1])
            pen.down()
            pen.setheading(_ * 72)  # 5个花瓣，每个72度

            # 向前画花瓣
            pen.forward(size / 2)

            # 画弧形形成花瓣
            pen.begin_fill()
            pen.circle(size / 4, 180)  # 半圆形作为花瓣
            pen.goto(pos[0], pos[1])  # 回到中心
            pen.end_fill()

    except Exception as err1:  # 修正：使用Exception而不是ExceptionGroup
        gui.msgbox(f"Exception:{err1}", "Error")
        return -1


def stick(pensize: int, size: int, pen, rad, facing, colour: str = "brown"):
    """
    绘制树枝
    size: 控制圆弧半径
    rad: 圆弧角度
    facing: 起始方向
    """
    global last_pos
    try:
        pen.color(colour)
        pen.pensize(pensize)
        pen.up()
        pen.goto(0, -100)
        pen.setheading(facing)
        pen.down()  # 添加这行，开始绘画
        pen.circle(size / 2, rad)
        last_pos = pen.position()
    except Exception as err2:  # 修正：使用Exception而不是ExceptionGroup
        gui.msgbox(f"Exception:{err2}", "Error")
        return -1


def main():
    global last_pos
    pen = t.Turtle()
    pen.speed("fastest")

    # 先画树枝
    stick(pensize=3, size=150, pen=pen, rad=30, facing=90, colour="brown")

    # 在树枝末端画花
    if last_pos:
        flower(colour="red", size=80, pen=pen, pos=[last_pos[0], last_pos[1]])

    turtle.done()


if __name__ == "__main__":
    main()