from django.db import models


class Tag(models.Model):
    name = models.CharField(default="name", max_length=20)


class Parent(models.Model):
    name = models.CharField(default="name", max_length=20)
    tags = models.ManyToManyField(Tag)

    class Meta:
        ordering = ["id"]


class Child(models.Model):
    name = models.CharField(default="name", max_length=20)

    class Meta:
        abstract = True
        ordering = ["id"]


class Child1(Child):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)


class Child2(Child):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)
