#imports
import turtle
import turtle as t
import easygui as gui
#define value
last_pos: int
#defines
def trangle(pensize:int, size:int, pen, colour:str="pink"):
    global last_pos
    try:
        pen.color(colour)
        pen.pensize(pensize)
        pen.forward(size)
def flower(colour:str, size:int, pen, pos:list, pensize:int):
    pen.speed("fastest")
    try:
        pen.pensize(pensize)
        pen.color(colour)
        pen.up()
        pen.goto(pos[0], pos[1])
        pen.down()
        pen.fillcolor(colour)
        pen.begin_fill()
        pen.circle(size/4)
        pen.end_fill()
        pen.goto(pos[0] + size / 2, pos[1] + size / 2)
        pen.left(93)
        pen.begin_fill()

        pen.end_fill()
    except Exception as err1:
        gui.msgbox(f"Exception:{err1}","Error")
        return -1

def stick(pensize:int, size:int, pen, rad, r, facing, colour:str="green"):
    global last_pos
    try:
        pen.color(colour)
        pen.pensize(pensize)
        pen.up()
        pen.goto(0,-100)
        pen.down()
        pen.setheading(facing)
        pen.circle(r, rad)
        last_pos = pen.position()
    except Exception as err2:
        gui.msgbox(f"Exception:{err2}","Error")
        return -1

def main():
    global last_pos
    pen = t.Turtle()
    stick(pensize=10, size=150000, pen=pen, rad=90, facing=45, r=50)
    gui.msgbox(f"last pos:{last_pos}","Debug")
    flower(colour="pink", size=50, pen=pen, pos=last_pos, pensize=1)

    turtle.done()


if __name__ == "__main__":
    main()